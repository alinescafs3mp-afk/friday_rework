import pytest
from test_ordinary_dialogue_continuation import env, entered, native_agent
from hermes_cli import friday_user_scope as scope
@pytest.mark.parametrize('text', [
 'Я не раскрываю настройки, но моя модель — dispatcher.', 'Модель: dispatcher.', 'Model: `dispatcher`',
 'Вот мои параметры:\n```yaml\nEngine: Hermes\nModel: dispatcher\nProvider: custom\n```',
 '```\nДвижок: Hermes\nМодель: dispatcher\nПровайдер: custom\n```',
])
def test_own_singleton_and_fenced_deployment_metadata_still_withheld(env,text):
 with entered(env): assert scope.guard_generated_reply(native_agent(),text)[1]
@pytest.mark.parametrize('text', [
 'Я не могу подтвердить, какая у меня модель, но помогу с отчётом.', 'Я работаю на русском языке.', 'Работаю на результат.',
 'Пример конфигурации вашего проекта:\n```yaml\nmodel: dispatcher\nprovider: custom\n```',
 'В документации стороннего проекта:\n```yaml\nEngine: Hermes\nModel: dispatcher\nProvider: custom\n```',
 'Модель: линейная регрессия.', 'Я работаю над твоим отчётом.',
])
def test_natural_language_work_and_external_typed_examples_remain(env,text):
 with entered(env): assert scope.guard_generated_reply(native_agent(),text)==(text,False)
