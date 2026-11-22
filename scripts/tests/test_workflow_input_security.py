"""Exercise workflow input quoting locally, without dispatching a workflow."""
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT=Path(__file__).resolve().parents[2]
class DeployInputTests(unittest.TestCase):
    def test_deployment_label_is_data_not_shell(self):
        source=(ROOT/'.github/workflows/deploy-canary.yml').read_text()
        script=textwrap.dedent(source.split('run: |',1)[1])
        # Only execute the label/logging prelude; never execute Docker/deployment.
        prelude=script.split('if ! command -v docker',1)[0]
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'injection-marker'
            label='$(printf injected > "$CANARY_TEST_MARKER") `printf also-injected`'
            rendered=prelude.replace('${{ inputs.environment }}',label)
            result=subprocess.run(['bash','-c',rendered],env=dict(os.environ,
                DEPLOY_LABEL=label,GIT_COMMIT='synthetic-review',CANARY_TEST_MARKER=str(marker)),
                capture_output=True,text=True,check=True)
            self.assertFalse(marker.exists(),'Deployment label executed shell syntax')
            self.assertIn(label,result.stdout)
            self.assertNotIn('${{ inputs.environment }}',prelude)
