import pytest
from test_ordinary_dialogue_continuation import env,entered,native_agent
from hermes_cli import friday_user_scope as scope
@pytest.mark.parametrize('text', [
 'My engine is Hermes and my provider is unknown.',
 'My provider is unknown and my engine is Hermes.',
 'Мой движок Hermes, а провайдер неизвестен.',
 'Мой провайдер неизвестен, а мой движок — Hermes.',
 'My model is dispatcher although my provider is unknown.',
 'Моя модель dispatcher, хотя мой провайдер неизвестен.',
 'My provider is unknown but my engine is Hermes.',
])
def test_each_positive_own_assertion_is_checked_despite_uncertain_other_slot(env,text):
 with entered(env):
  assert scope.guard_generated_reply(native_agent(),text)[1]
  assert scope.LEGACY_SELF_CLAIM_VIEW in scope.project_legacy_self_claims([{'role':'assistant','content':text}])[0]['content']
@pytest.mark.parametrize('text', [
 'My engine is unknown and my provider is unknown.',
 'Мой движок неизвестен, а мой провайдер неизвестен.',
 'I cannot confirm my model, but I can help with your report.',
 'Я не могу подтвердить, какая у меня модель, но помогу с отчётом.',
 'Для вашего проекта Hermes работает на Linux; provider=custom.',
])
def test_uncertainty_and_external_tasks_still_accepted(env,text):
 with entered(env): assert scope.guard_generated_reply(native_agent(),text)==(text,False)
