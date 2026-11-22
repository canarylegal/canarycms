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

    def test_memory_trend_separates_interleaved_containers_and_ignores_single_peak(self):
        rows=[]
        for a,b in zip([10,10,200,20,30,30],[90,90,60,60,40,40]):
            for name,value in [('backend',a),('db',b)]:
                rows.append(json.dumps({'Name':name,'MemUsage':f'{value}MiB / 2GiB','CPUPerc':'1%'}))
        _,summary=module.normalize('\n'.join(rows))
        self.assertEqual(summary['backend']['peak_memory_bytes'],200*2**20)
        self.assertEqual(summary['backend']['median_memory_growth_bytes'],20*2**20)
        self.assertEqual(summary['db']['median_memory_growth_bytes'],-50*2**20)
