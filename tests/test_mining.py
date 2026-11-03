import copy
import unittest
from mining.lab import digest, keypair, sign, verify, experiment, valid

class MiningTests(unittest.TestCase):
 def test_sm3_known_vector(self):
  self.assertEqual(digest(b'abc').hex(),'66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0')
 def test_signature_and_tamper(self):
  signer,public=keypair();a=sign(signer,b'course');b=sign(signer,b'course')
  self.assertNotEqual(a,b);self.assertTrue(verify(public,b'course',a));self.assertFalse(verify(public,b'fake',a))
 def test_real_pow_and_power_boundary(self):
  r=experiment(2,8,2,1)
  self.assertEqual(r['summary']['successes'],2);self.assertTrue(valid(r['sample']))
  for row in r['rows']:
   self.assertEqual(sum(w['attempts'] for w in row['workers']),row['hashes'])
   self.assertIsNone(row['energy_j']);self.assertIsNone(row['measured_system_w'])
  bad=copy.deepcopy(r['sample']);bad['transaction']['body']['amount']=999;self.assertFalse(valid(bad))
  r=experiment(1,8,1,1,50);self.assertAlmostEqual(r['rows'][0]['energy_j'],r['rows'][0]['elapsed_s']*50)
 def test_bad_parameters(self):
  for kw in ({'nodes':True},{'nodes':100},{'watts':float('nan')},{'watts':0},{'difficulty':256}):
   with self.assertRaises(ValueError):experiment(**kw)
