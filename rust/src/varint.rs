/// Decode unsigned varint from buf starting at offset.
/// Returns (value, bytes_consumed) or error if buffer too short / overflow.
#[inline]
pub fn decode_uvarint(buf: &[u8], offset: usize) -> Result<(u64, usize), &'static str> {
    let mut result: u64 = 0;
    let mut shift: u32 = 0;
    let len = buf.len();
    let mut i = offset;

    loop {
        if i >= len {
            return Err("buffer too short for uvarint");
        }
        let b = buf[i];
        i += 1;

        // Check for overflow before shifting
        if shift >= 63 && b > 1 {
            return Err("uvarint overflow");
        }

        result |= ((b & 0x7F) as u64) << shift;

        if (b & 0x80) == 0 {
            return Ok((result, i - offset));
        }
        shift += 7;
    }
}

/// Decode shifted varint (value >> 1).
#[inline]
pub fn decode_shifted_varint(buf: &[u8], offset: usize) -> Result<(u64, usize), &'static str> {
    let (val, consumed) = decode_uvarint(buf, offset)?;
    Ok((val >> 1, consumed))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zero() {
        let (val, n) = decode_uvarint(&[0x00], 0).unwrap();
        assert_eq!(val, 0);
        assert_eq!(n, 1);
    }

    #[test]
    fn test_single_byte() {
        let (val, n) = decode_uvarint(&[0x01], 0).unwrap();
        assert_eq!(val, 1);
        assert_eq!(n, 1);

        let (val, n) = decode_uvarint(&[0x7F], 0).unwrap();
        assert_eq!(val, 127);
        assert_eq!(n, 1);
    }

    #[test]
    fn test_multi_byte() {
        // 300 = 0xAC 0x02
        let (val, n) = decode_uvarint(&[0xAC, 0x02], 0).unwrap();
        assert_eq!(val, 300);
        assert_eq!(n, 2);
    }

    #[test]
    fn test_with_offset() {
        let buf = [0xFF, 0x01, 0x00]; // offset 1 -> value 1, offset 2 -> value 0
        let (val, n) = decode_uvarint(&buf, 1).unwrap();
        assert_eq!(val, 1);
        assert_eq!(n, 1);
    }

    #[test]
    fn test_empty_buffer() {
        assert!(decode_uvarint(&[], 0).is_err());
    }

    #[test]
    fn test_buffer_too_short() {
        // 0x80 means continuation but no next byte
        assert!(decode_uvarint(&[0x80], 0).is_err());
    }

    #[test]
    fn test_shifted() {
        // uvarint 10 >> 1 = 5
        let (val, n) = decode_shifted_varint(&[0x0A], 0).unwrap();
        assert_eq!(val, 5);
        assert_eq!(n, 1);
    }
}
