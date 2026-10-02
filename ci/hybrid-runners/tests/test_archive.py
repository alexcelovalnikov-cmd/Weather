import io
import pathlib
import tarfile
import tempfile
import unittest
from hybrid.archive import extract_runner

class ArchiveTests(unittest.TestCase):
 def run_archive(self, entries):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);dest=root/'guest';dest.mkdir();arc=root/'runner.tar'
   with tarfile.open(arc,'w') as tf:
    for name,kind,target in entries:
     m=tarfile.TarInfo(name)
     if kind=='link':m.type=tarfile.SYMTYPE;m.linkname=target;tf.addfile(m)
     else:m.size=len(target);tf.addfile(m,io.BytesIO(target))
   extract_runner(arc,dest)
   return [(str(p.relative_to(dest)),p.is_symlink()) for p in dest.rglob('*')]
 def test_official_internal_node_link(self):
  result=self.run_archive([('externals/node24/lib/npm.js','file',b'node'),
                           ('externals/node24/bin/npm','link','../lib/npm.js')])
  self.assertIn(('externals/node24/bin/npm',True),result)
 def test_member_escape_rejected(self):
  with self.assertRaises(ValueError):self.run_archive([('../outside','file',b'x')])
 def test_absolute_link_rejected(self):
  with self.assertRaises(ValueError):self.run_archive([('npm','link','/tmp/outside')])
 def test_relative_link_escape_rejected(self):
  with self.assertRaises(ValueError):self.run_archive([('npm','link','../../outside')])
 def test_write_through_link_rejected(self):
  with self.assertRaises(ValueError):self.run_archive([('dir','link','other'),('dir/file','file',b'x')])
