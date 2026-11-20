from types import SimpleNamespace
import pytest
from scripts import seed_performance_fixture as fixture

@pytest.mark.parametrize('database,test_flag,performance_flag',[
    ('canary','1','1'),('canary_core_test','0','1'),('canary_core_test','1','0'),('canary_recovery','1','1')])
def test_scale_fixture_refuses_existing_deployment_or_missing_explicit_flags(monkeypatch,database,test_flag,performance_flag):
    monkeypatch.setattr(fixture,'engine',SimpleNamespace(url=SimpleNamespace(database=database)))
    monkeypatch.setenv('CANARY_TEST_FIXTURE',test_flag)
    monkeypatch.setenv('CANARY_PERFORMANCE_FIXTURE',performance_flag)
    with pytest.raises(RuntimeError,match='dedicated core-test'): fixture.guard()
