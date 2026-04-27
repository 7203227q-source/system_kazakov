# Спецификация: Система сообщений (Мессенджер)

## 1. Обзор
Внутренняя система обмена сообщениями (P2P) между пользователями платформы:
- Репетитор ↔ Ученик
- Репетитор ↔ Родитель

Реализация: **AJAX Polling** (псевдо-реальное время) с поддержкой вложений (Текст + Файлы/Изображения).

## 2. Модель данных (DB Schema)
Добавление новой модели в `core/models.py`:

```python
class Message(models.Model):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField(blank=True, null=True, verbose_name="Текст сообщения")
    attachment = models.FileField(upload_to='chat_attachments/', blank=True, null=True, verbose_name="Вложение (Файл/Фото)")
    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время отправки")

    class Meta:
        ordering = ['created_at']
```

## 3. Интерфейс (UI/UX)
- **Навигация**: В боковом меню (Sidebar) добавляется пункт "Сообщения" с бейджем непрочитанных.
- **Страница Чата (`core/chat.html`)**:
  - *Левая колонка*: Список диалогов (пользователи, с которыми есть связь: ученики для репетитора, репетиторы для ученика и родителя). Сортировка по времени последнего сообщения. Индикатор непрочитанных.
  - *Правая колонка*: Окно переписки.
    - История сообщений (свои сообщения справа, чужие слева).
    - Если вложение - картинка (`.jpg`, `.png`), отображать превью. Если документ (`.pdf`, `.docx`) - кнопку скачивания.
    - Поле ввода текста + кнопка "Прикрепить файл" (Скрепка) + кнопка "Отправить".

## 4. API (Backend)
Реализация REST-подобных эндпоинтов для AJAX:
- `GET /chat/api/dialogs/` — Получить список диалогов (с последним сообщением и кол-вом непрочитанных).
- `GET /chat/api/messages/<user_id>/` — Получить историю переписки с конкретным пользователем. Помечает полученные сообщения как прочитанные.
- `POST /chat/api/send/<user_id>/` — Отправить новое сообщение (принимает `multipart/form-data` для файлов).
- `GET /chat/api/unread_count/` — Глобальный счетчик непрочитанных для Sidebar.

## 5. Логика Polling (Frontend JS)
- На странице чата скрипт раз в 3 секунды запрашивает `/chat/api/messages/<active_user_id>/?after=<last_msg_id>` для получения только новых сообщений.
- При получении новых сообщений они добавляются в DOM, а скролл опускается вниз.
- Глобальный скрипт (в `base.html`) раз в 30 секунд обновляет бейдж в Sidebar.