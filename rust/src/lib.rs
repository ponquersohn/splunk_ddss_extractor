use pyo3::prelude::*;

mod decoder;
mod varint;

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(decoder::scan_batch, m)?)?;
    m.add_class::<decoder::ScanState>()?;
    Ok(())
}
