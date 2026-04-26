# План реализации: Авторизация через соцсети (Google, VK) с выбором роли

## 1. Подготовка окружения (django-allauth)
1. Установить пакет `django-allauth`.
2. Добавить его в `requirements.txt`.
3. Обновить `settings.py`:
   - Добавить `allauth`, `allauth.account`, `allauth.socialaccount`, `allauth.socialauth.providers.google`, `allauth.socialauth.providers.vk` в `INSTALLED_APPS`.
   - Добавить `allauth.account.middleware.AccountMiddleware` в `MIDDLEWARE`.
   - Настроить бэкенды аутентификации (включить `allauth`).
   - Задать настройки `SITE_ID = 1`, отключить обязательное подтверждение email (`ACCOUNT_EMAIL_VERIFICATION = 'none'`).
4. Добавить маршруты `allauth` в `urls.py` проекта.

## 2. Изменение модели User
1. В `core/models.py` изменить `ROLE_CHOICES`: добавить `('unassigned', 'Не выбрана')`.
2. Изменить `default='unassigned'` для поля `role` (по умолчанию новые пользователи будут получать эту роль, а наша форма регистрации явно задает `student`).
3. Создать и применить миграции (`makemigrations`, `migrate`).

## 3. Страница выбора роли (/select-role/)
1. В `core/views.py` создать `role_selection_view(request)`:
   - Должна требовать авторизации (`@login_required`).
   - Если у пользователя роль уже не `unassigned`, редиректить его на нужный дашборд.
   - Если POST-запрос с выбранной ролью (student/tutor/parent) — обновить `request.user.role`, сохранить и редиректнуть.
   - Если GET-запрос — отрендерить шаблон `select_role.html`.
2. Создать шаблон `core/templates/core/select_role.html` с тремя большими карточками (Ученик, Репетитор, Родитель) и формой для отправки POST-запроса.
3. Добавить маршрут `path('select-role/', views.role_selection_view, name='select_role')` в `urls.py`.

## 4. Кастомный адаптер Allauth (Редирект)
1. Создать файл `core/adapters.py`.
2. Написать класс `CustomAccountAdapter(DefaultAccountAdapter)`, переопределив метод `get_login_redirect_url(self, request)`:
   - Если `user.role == 'unassigned'`, возвращать `reverse('select_role')`.
   - Иначе возвращать ссылку на дашборд в зависимости от роли.
3. В `settings.py` указать `ACCOUNT_ADAPTER = 'core.adapters.CustomAccountAdapter'`.

## 5. Обновление UI
1. В `core/templates/core/login.html` и `register.html` заменить кнопки-заглушки соцсетей на реальные ссылки `{% provider_login_url 'google' %}` и `{% provider_login_url 'vk' %}`.

## 6. Деплой и финализация
1. Закоммитить изменения.
2. Отправить на GitHub для деплоя на VPS.
