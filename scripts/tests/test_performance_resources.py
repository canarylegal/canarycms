import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('performance_resources',Path(__file__).parents[1]/'summarize_performance_resources.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ResourceSamplesTests(unittest.TestCase):
    def test_real_terminal_sequences_and_truncated_final_sample(self):
        row={'Name':'canaryperf-fixture-backend-1','MemUsage':'152.3MiB / 2GiB','CPUPerc':'17.45%'}
        raw='\x1b[H'+json.dumps(row)+'\x1b[K\n\x1b[J\n'+json.dumps(row)+'\n{"Name":'
        samples,summary=module.normalize(raw)
        self.assertEqual(len(samples),2)
        self.assertEqual(samples[0]['memory_bytes'],int(152.3*2**20))
        self.assertEqual(samples[0]['limit_bytes'],2*2**30)
        self.assertEqual(summary[row['Name']]['peak_cpu_percent'],17.45)
    def test_missing_measurements_fail_instead_of_publishing_empty_evidence(self):
        with self.assertRaises(RuntimeError):module.normalize('Docker is unavailable\n')
