"""Normalize Docker's streaming terminal output into machine-readable samples."""
import json
from pathlib import Path
import re
import sys
from statistics import median

ANSI=re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

def byte_count(value):
    units={'GiB':2**30,'MiB':2**20,'KiB':2**10,'GB':10**9,'MB':10**6,'kB':10**3,'B':1}
    for unit,multiplier in units.items():
        if value.strip().endswith(unit): return int(float(value.strip()[:-len(unit)])*multiplier)
    raise ValueError('Unknown Docker memory unit')

def normalize(raw):
    samples=[];summary={}
    for line in ANSI.sub('',raw).splitlines():
        try: row=json.loads(line)
        except ValueError: continue  # Empty terminal lines or interrupted final sample.
        if not isinstance(row,dict) or 'MemUsage' not in row: continue
        used,limit=row['MemUsage'].split('/')
        sample={'container':row['Name'],'memory_bytes':byte_count(used),'limit_bytes':byte_count(limit),
                'cpu_percent':float(row['CPUPerc'].rstrip('%'))}
        samples.append(sample)
        peak=summary.setdefault(row['Name'],{'samples':0,'peak_memory_bytes':0,'peak_cpu_percent':0})
        peak['samples']+=1
        peak['peak_memory_bytes']=max(peak['peak_memory_bytes'],sample['memory_bytes'])
        peak['peak_cpu_percent']=max(peak['peak_cpu_percent'],sample['cpu_percent'])
    if not samples: raise RuntimeError('No resource samples were collected.')
    for name, peak in summary.items():
        memory = [row['memory_bytes'] for row in samples if row['container'] == name]
        window = max(1, len(memory) // 3)
        peak['first_third_median_memory_bytes'] = int(median(memory[:window]))
        peak['last_third_median_memory_bytes'] = int(median(memory[-window:]))
        peak['median_memory_growth_bytes'] = peak['last_third_median_memory_bytes'] - peak['first_third_median_memory_bytes']
    return samples,summary

if __name__=='__main__':
    root=Path(sys.argv[1])
    samples,summary=normalize((root/'resource-samples.raw').read_text())
    (root/'resource-samples.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in samples))
    (root/'resource-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (root/'resource-samples.raw').unlink()
