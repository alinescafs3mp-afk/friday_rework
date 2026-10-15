import pytest
from test_ordinary_dialogue_continuation import env,entered,native_agent
from hermes_cli import friday_user_scope as scope
@pytest.mark.parametrize('text', [
 'My engine is Hermes, provider unknown.', 'Мой движок Hermes, провайдер неизвестен.',
 'My engine is Hermes (provider unknown).', 'My engine is Hermes with unknown provider.',
 "My engine is Hermes (I don't know my provider).",
 'My provider is unknown, my engine is Hermes.',
 'Engine: Hermes (provider unknown)\nModel: unknown',
 'Движок: Hermes, провайдер неизвестен.\nМодель: неизвестна',
])
def test_uncertainty_never_excuses_other_positive_slot_value(env,text):
 with entered(env):
  assert scope.guard_generated_reply(native_agent(),text)[1]
  assert scope.LEGACY_SELF_CLAIM_VIEW in scope.project_legacy_self_claims([{'role':'assistant','content':text}])[0]['content']
@pytest.mark.parametrize('text', [
 "I don't know my model or provider.", 'I cannot confirm my model and provider.',
 'Я не знаю, какая у меня модель и провайдер.', 'My model is not disclosed; I can help with the report.',
 'My engine is unknown (provider unknown).',
 'My engine is unknown with unknown provider.',
 'Engine: unknown\nModel: unknown\nProvider: unknown',
 'Я не могу подтвердить, какая у меня модель. Я — Пятница.',
])
def test_field_local_honest_unknown_remains_safe(env,text):
 with entered(env): assert scope.guard_generated_reply(native_agent(),text)==(text,False)
