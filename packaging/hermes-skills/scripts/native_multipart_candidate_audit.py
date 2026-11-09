"""Read-only native multipart audit. Never submits, uploads or retains security parts."""
import email
import email.policy

def candidate_parts(body, allowed_text, allowed_files):
    """Project whitelisted fields and file names; preserve actual MIME boundary hyphens."""
    if isinstance(body, str):
        body = body.encode('utf-8')
    first = body.split(b'\r\n', 1)[0]
    if not first.startswith(b'--'):
        raise ValueError('No multipart opening delimiter')
    boundary = first[2:]
    if not boundary or b'\n' in boundary:
        raise ValueError('Invalid multipart boundary')
    envelope = b'Content-Type: multipart/form-data; boundary="' + boundary + b'"\r\nMIME-Version: 1.0\r\n\r\n' + body
    msg = email.message_from_bytes(envelope, policy=email.policy.default)
    if not msg.is_multipart():
        raise ValueError('Expected actual multipart parts')
    out = {}
    for part in msg.iter_parts():
        name = part.get_param('name', header='content-disposition')
        if name not in allowed_text and name not in allowed_files:
            continue
        if name in out:
            raise ValueError('Repeated candidate field: ' + name)
        if name in allowed_files:
            out[name] = {'filename': part.get_filename(), 'content_type': part.get_content_type()}
        else:
            value = part.get_content()
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            out[name] = value.replace('\r\n', '\n')
    if not out:
        raise ValueError('Empty candidate projection, keep original CDP session open')
    return out

if __name__ == '__main__':
    import unittest
    class AuditTests(unittest.TestCase):
        def test_webkit_boundary_and_exclusions(self):
            boundary = '----WebKitFormBoundarySyntheticFixture'
            body = '\r\n'.join(['--'+boundary,'Content-Disposition: form-data; name="message"','','First line\r\nSecond line','--'+boundary,'Content-Disposition: form-data; name="resume"; filename="Approved-Fixture.pdf"','Content-Type: application/pdf','','synthetic-file-fixture','--'+boundary,'Content-Disposition: form-data; name="csrf"','','synthetic-excluded-security-fixture','--'+boundary+'--',''])
            got = candidate_parts(body, {'message'}, {'resume'})
            self.assertEqual(got['message'], 'First line\nSecond line')
            self.assertEqual(got['resume']['filename'], 'Approved-Fixture.pdf')
            self.assertNotIn('csrf', got)
        def test_empty_projection_fails(self):
            with self.assertRaises(ValueError):
                candidate_parts('--example\r\nContent-Disposition: form-data; name="csrf"\r\n\r\nfixture\r\n--example--\r\n', {'name'}, {'resume'})
    unittest.main()
