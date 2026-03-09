use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::varint::{decode_shifted_varint, decode_uvarint};

// Opcode constants
const OP_NOP: u8 = 0;
const OP_OLDSTYLE_EVENT: u8 = 1;
const OP_OLDSTYLE_EVENT_WITH_HASH: u8 = 2;
const OP_NEW_HOST: u8 = 3;
const OP_NEW_SOURCE: u8 = 4;
const OP_NEW_SOURCE_TYPE: u8 = 5;
const OP_NEW_STRING: u8 = 6;
const OP_SPLUNK_PRIVATE: u8 = 9;
const OP_HEADER: u8 = 10;

const HASH_SIZE: usize = 20;

fn rmki_extra_ints(key: u64) -> usize {
    match key {
        0 => 1, 2 => 1, 3 => 2, 4 => 2, 6 => 2, 7 => 3,
        8 => 1, 9 => 1, 10 => 1, 11 => 2, 12 => 3, 14 => 2, 15 => 0,
        _ => 0,
    }
}

#[inline]
fn is_event_opcode(op: u8) -> bool {
    op == OP_OLDSTYLE_EVENT || op == OP_OLDSTYLE_EVENT_WITH_HASH || (32..=43).contains(&op)
}

#[pyclass]
pub struct ScanState {
    fields: Vec<Vec<String>>,
    base_event_time: i32,
    base_index_time: i32,
    active_host: usize,
    active_source: usize,
    active_source_type: usize,
    #[pyo3(get)]
    total_metadata_errors: usize,
    #[pyo3(get)]
    events_with_errors: usize,
    leftover: Vec<u8>,
    /// Absolute stream position, persistent across scan_batch calls.
    abs_pos: usize,
}

#[pymethods]
impl ScanState {
    #[new]
    fn new() -> Self {
        let mut fields = Vec::with_capacity(7);
        for _ in 0..7 {
            fields.push(Vec::new());
        }
        ScanState {
            fields,
            base_event_time: 0,
            base_index_time: 0,
            active_host: 0,
            active_source: 0,
            active_source_type: 0,
            total_metadata_errors: 0,
            events_with_errors: 0,
            leftover: Vec::new(),
            abs_pos: 0,
        }
    }
}

impl ScanState {
    fn get_host(&self) -> &str {
        if self.active_host > 0 {
            self.fields[OP_NEW_HOST as usize].get(self.active_host - 1).map_or("", |s| s.as_str())
        } else { "" }
    }
    fn get_source(&self) -> &str {
        if self.active_source > 0 {
            self.fields[OP_NEW_SOURCE as usize].get(self.active_source - 1).map_or("", |s| s.as_str())
        } else { "" }
    }
    fn get_source_type(&self) -> &str {
        if self.active_source_type > 0 {
            self.fields[OP_NEW_SOURCE_TYPE as usize].get(self.active_source_type - 1).map_or("", |s| s.as_str())
        } else { "" }
    }

    #[inline]
    fn advance(&mut self, n: usize) {
        self.abs_pos += n;
    }
}

enum DecodeResult {
    Event(EventData),
    Continue,
    NeedMore,
    Error(String),
}

struct EventData {
    index_time: i64,
    event_time: i64,
    message: String,
    host: String,
    source: String,
    sourcetype: String,
    fields: Vec<(String, FieldValue)>,
    extraction_errors: Vec<String>,
}

enum FieldValue {
    Single(String),
    List(Vec<String>),
}

#[pyfunction]
pub fn scan_batch<'py>(
    py: Python<'py>,
    state: &mut ScanState,
    buf: &[u8],
) -> PyResult<Bound<'py, PyDict>> {
    let leftover_len = state.leftover.len();
    let working: Vec<u8>;
    let work_buf: &[u8];
    if leftover_len == 0 {
        work_buf = buf;
    } else {
        working = [state.leftover.as_slice(), buf].concat();
        work_buf = &working;
    }
    state.leftover.clear();

    // abs_pos already points to the start of the leftover region
    // (rewound by NeedMore handling), so no adjustment needed.

    let mut pos: usize = 0;
    let mut events: Vec<EventData> = Vec::new();
    let mut error_msg: Option<String> = None;

    while pos < work_buf.len() {
        let opcode = work_buf[pos];
        let opcode_start_pos = pos;
        let opcode_start_abs = state.abs_pos;
        pos += 1;
        state.abs_pos += 1;

        if opcode == OP_NOP {
            continue;
        }

        let result = dispatch_opcode(state, work_buf, &mut pos, opcode);

        match result {
            DecodeResult::Continue => {}
            DecodeResult::Event(ev) => events.push(ev),
            DecodeResult::NeedMore => {
                pos = opcode_start_pos;
                state.abs_pos = opcode_start_abs;
                break;
            }
            DecodeResult::Error(msg) => {
                error_msg = Some(msg);
                break;
            }
        }
    }

    if pos < work_buf.len() {
        state.leftover = work_buf[pos..].to_vec();
    }

    let result = PyDict::new(py);
    let py_events = PyList::empty(py);
    for ev in &events {
        py_events.append(event_to_pydict(py, ev)?)?;
    }
    result.set_item("events", py_events)?;
    result.set_item("consumed", pos)?;
    match error_msg {
        Some(ref msg) => result.set_item("error", msg)?,
        None => result.set_item("error", py.None())?,
    }
    Ok(result)
}

fn dispatch_opcode(
    state: &mut ScanState,
    buf: &[u8],
    pos: &mut usize,
    opcode: u8,
) -> DecodeResult {
    match opcode {
        OP_HEADER => decode_header(state, buf, pos),
        OP_SPLUNK_PRIVATE => decode_splunk_private(state, buf, pos),
        OP_NEW_HOST | OP_NEW_SOURCE | OP_NEW_SOURCE_TYPE | OP_NEW_STRING =>
            decode_string_field(state, buf, pos, opcode),
        17..=31 => decode_new_state(state, buf, pos, opcode),
        op if is_event_opcode(op) => decode_event(state, buf, pos, opcode),
        _ => DecodeResult::Error(format!("Unknown opcode: 0x{:02x}", opcode)),
    }
}

fn decode_header(state: &mut ScanState, buf: &[u8], pos: &mut usize) -> DecodeResult {
    if *pos + 6 > buf.len() { return DecodeResult::NeedMore; }
    state.base_index_time = i32::from_le_bytes([buf[*pos+2], buf[*pos+3], buf[*pos+4], buf[*pos+5]]);
    *pos += 6;
    state.advance(6);
    DecodeResult::Continue
}

fn decode_splunk_private(state: &mut ScanState, buf: &[u8], pos: &mut usize) -> DecodeResult {
    match decode_uvarint(buf, *pos) {
        Ok((length, n)) => {
            let total = n + length as usize;
            if *pos + total > buf.len() { return DecodeResult::NeedMore; }
            *pos += total;
            state.advance(total);
            DecodeResult::Continue
        }
        Err(_) => DecodeResult::NeedMore,
    }
}

fn decode_string_field(state: &mut ScanState, buf: &[u8], pos: &mut usize, opcode: u8) -> DecodeResult {
    match decode_uvarint(buf, *pos) {
        Ok((length, n)) => {
            let str_len = length as usize;
            if *pos + n + str_len > buf.len() { return DecodeResult::NeedMore; }
            let s = String::from_utf8_lossy(&buf[*pos + n..*pos + n + str_len]).into_owned();
            let consumed = n + str_len;
            *pos += consumed;
            state.advance(consumed);
            let idx = opcode as usize;
            if idx < state.fields.len() {
                state.fields[idx].push(s);
            }
            DecodeResult::Continue
        }
        Err(_) => DecodeResult::NeedMore,
    }
}

fn decode_new_state(state: &mut ScanState, buf: &[u8], pos: &mut usize, opcode: u8) -> DecodeResult {
    let saved_pos = *pos;
    let saved_abs = state.abs_pos;

    macro_rules! try_uvarint {
        () => {
            match decode_uvarint(buf, *pos) {
                Ok((val, n)) => { *pos += n; state.advance(n); val as usize }
                Err(_) => { *pos = saved_pos; state.abs_pos = saved_abs; return DecodeResult::NeedMore; }
            }
        };
    }

    if opcode & 0x8 != 0 { state.active_host = try_uvarint!(); }
    if opcode & 0x4 != 0 { state.active_source = try_uvarint!(); }
    if opcode & 0x2 != 0 { state.active_source_type = try_uvarint!(); }
    if opcode & 0x1 != 0 {
        if *pos + 4 > buf.len() { *pos = saved_pos; state.abs_pos = saved_abs; return DecodeResult::NeedMore; }
        state.base_event_time = i32::from_le_bytes([buf[*pos], buf[*pos+1], buf[*pos+2], buf[*pos+3]]);
        *pos += 4;
        state.advance(4);
    }
    DecodeResult::Continue
}

fn decode_event(state: &mut ScanState, buf: &[u8], pos: &mut usize, opcode: u8) -> DecodeResult {
    let event_start_pos = *pos;
    let event_start_abs = state.abs_pos;

    macro_rules! rewind {
        () => { *pos = event_start_pos; state.abs_pos = event_start_abs; return DecodeResult::NeedMore; };
    }

    macro_rules! try_uvarint {
        () => {
            match decode_uvarint(buf, *pos) {
                Ok((val, n)) => { *pos += n; state.advance(n); val }
                Err(_) => { rewind!(); }
            }
        };
    }

    macro_rules! need {
        ($n:expr) => { if *pos + $n > buf.len() { rewind!(); } };
    }

    // Message length wire value
    let msg_len_wire = try_uvarint!();
    let msg_end_abs = msg_len_wire as usize + state.abs_pos;

    // Extended storage
    let mut has_extended_storage = false;
    let mut extended_storage_len: usize = 0;
    if opcode & 0x4 != 0 {
        has_extended_storage = true;
        extended_storage_len = try_uvarint!() as usize;
    }

    // Hash
    if opcode & 0x01 == 0 {
        need!(HASH_SIZE);
        *pos += HASH_SIZE;
        state.advance(HASH_SIZE);
    }

    // Stream ID (uint64 LE) — skip
    need!(8);
    *pos += 8;
    state.advance(8);

    // Stream offset — skip
    let _ = try_uvarint!();
    // Stream sub offset — skip
    let _ = try_uvarint!();

    // index_time_diff
    let index_time_diff = try_uvarint!();
    let index_time = state.base_index_time as i64 + index_time_diff as i64;

    // Sub seconds (shifted varint)
    let time_sub_seconds = match decode_shifted_varint(buf, *pos) {
        Ok((val, n)) => { *pos += n; state.advance(n); val }
        Err(_) => { rewind!(); }
    };
    let event_time = state.base_event_time as i64 * 1000 + time_sub_seconds as i64;

    // Metadata count
    let metadata_count = try_uvarint!() as usize;

    // Decode metadata
    let mut meta_fields: Vec<(String, FieldValue)> = Vec::new();
    let mut extraction_errors: Vec<String> = Vec::new();

    for i in 0..metadata_count {
        match decode_one_metadata(state, buf, pos, opcode, event_start_pos, event_start_abs) {
            MetaResult::Ok(entries) => {
                for (field_idx, value_idx) in entries {
                    match decode_field(state, field_idx, value_idx) {
                        FieldResult::Ok(key, val) => {
                            if let Some(existing) = meta_fields.iter_mut().find(|(k, _)| k == &key) {
                                match &mut existing.1 {
                                    FieldValue::Single(old) => {
                                        let old_val = old.clone();
                                        existing.1 = FieldValue::List(vec![old_val, val]);
                                    }
                                    FieldValue::List(list) => list.push(val),
                                }
                            } else {
                                meta_fields.push((key, FieldValue::Single(val)));
                            }
                        }
                        FieldResult::Error(msg) => extraction_errors.push(msg),
                    }
                }
            }
            MetaResult::NeedMore => { rewind!(); }
            MetaResult::Error(msg) => {
                extraction_errors.push(format!("metadata entry {}: {}", i, msg));
                state.total_metadata_errors += 1;
            }
        }
    }

    if !extraction_errors.is_empty() {
        state.events_with_errors += 1;
    }

    // Extended storage: skip
    if has_extended_storage {
        need!(extended_storage_len);
        *pos += extended_storage_len;
        state.advance(extended_storage_len);
    }

    // Read message
    let actual_msg_len = msg_end_abs.saturating_sub(state.abs_pos);
    need!(actual_msg_len);
    let message = String::from_utf8_lossy(&buf[*pos..*pos + actual_msg_len]).into_owned();
    *pos += actual_msg_len;
    state.advance(actual_msg_len);

    DecodeResult::Event(EventData {
        index_time,
        event_time,
        message,
        host: state.get_host().to_owned(),
        source: state.get_source().to_owned(),
        sourcetype: state.get_source_type().to_owned(),
        fields: meta_fields,
        extraction_errors,
    })
}

enum MetaResult {
    Ok(Vec<(u64, u64)>),
    NeedMore,
    Error(String),
}

fn decode_one_metadata(
    state: &mut ScanState,
    buf: &[u8],
    pos: &mut usize,
    opcode: u8,
    event_start_pos: usize,
    event_start_abs: usize,
) -> MetaResult {
    macro_rules! rewind {
        () => { *pos = event_start_pos; state.abs_pos = event_start_abs; return MetaResult::NeedMore; };
    }

    let (meta_key_raw, n) = match decode_uvarint(buf, *pos) {
        Ok(v) => v,
        Err(_) => { rewind!(); }
    };
    *pos += n;
    state.advance(n);

    let (rest, num_to_read) = if opcode <= 2 {
        let meta_key = meta_key_raw << 3;
        (meta_key >> 4, 1usize)
    } else {
        let meta_key = if opcode < 36 { meta_key_raw << 2 } else { meta_key_raw };
        let rmki_key = meta_key & 0xF;
        (meta_key >> 4, rmki_extra_ints(rmki_key))
    };

    let mut entries = Vec::with_capacity(num_to_read);
    for _ in 0..num_to_read {
        match decode_uvarint(buf, *pos) {
            Ok((val, n)) => {
                entries.push((rest, val));
                *pos += n;
                state.advance(n);
            }
            Err(_) => { rewind!(); }
        }
    }

    MetaResult::Ok(entries)
}

enum FieldResult {
    Ok(String, String),
    Error(String),
}

fn decode_field(state: &ScanState, key: u64, value: u64) -> FieldResult {
    if key == 0 || value == 0 {
        return FieldResult::Error(format!("key={}, value={}: zero index", key, value));
    }
    let key_idx = (key - 1) as usize;
    let val_idx = (value - 1) as usize;
    let strings = &state.fields[OP_NEW_STRING as usize];
    match (strings.get(key_idx), strings.get(val_idx)) {
        (Some(k), Some(v)) => FieldResult::Ok(k.clone(), v.clone()),
        _ => FieldResult::Error(format!(
            "key={}, value={}: index out of range (strings len={})", key, value, strings.len()
        )),
    }
}

fn event_to_pydict<'py>(py: Python<'py>, ev: &EventData) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("index_time", ev.index_time)?;
    d.set_item("time", ev.event_time)?;
    d.set_item("event", &ev.message)?;
    d.set_item("host", &ev.host)?;
    d.set_item("sourcetype", &ev.sourcetype)?;
    d.set_item("source", &ev.source)?;

    let fields = PyDict::new(py);
    for (key, val) in &ev.fields {
        match val {
            FieldValue::Single(s) => fields.set_item(key, s)?,
            FieldValue::List(list) => fields.set_item(key, PyList::new(py, list)?)?,
        }
    }
    if !ev.extraction_errors.is_empty() {
        fields.set_item("__extraction_errors__", PyList::new(py, &ev.extraction_errors)?)?;
    }
    d.set_item("fields", fields)?;
    Ok(d)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_event_opcode() {
        assert!(!is_event_opcode(0));
        assert!(is_event_opcode(1));
        assert!(is_event_opcode(2));
        assert!(!is_event_opcode(3));
        assert!(is_event_opcode(32));
        assert!(is_event_opcode(43));
        assert!(!is_event_opcode(44));
    }

    #[test]
    fn test_rmki_extra_ints() {
        assert_eq!(rmki_extra_ints(0), 1);
        assert_eq!(rmki_extra_ints(8), 1);
        assert_eq!(rmki_extra_ints(4), 2);
        assert_eq!(rmki_extra_ints(7), 3);
        assert_eq!(rmki_extra_ints(15), 0);
        assert_eq!(rmki_extra_ints(99), 0);
    }
}
