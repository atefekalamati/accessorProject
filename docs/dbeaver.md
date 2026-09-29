# اتصال DBeaver به PostgreSQL پروژه Project AK

## اطلاعات اتصال

| گزینه | مقدار |
|---|---|
| Driver | PostgreSQL |
| Host | `localhost` |
| Port | مقدار `DB_HOST_PORT` در `.env` (پیش‌فرض `5432`) |
| Database | `project_ak` |
| Username | `project_ak` |
| Password | مقدار `POSTGRES_PASSWORD` در فایل محلی `.env` |

در DBeaver گزینه **New Database Connection** و سپس PostgreSQL را انتخاب کنید. مقادیر جدول بالا را وارد کنید، در صورت درخواست driver را دانلود کنید و با **Test Connection** اتصال را بررسی کنید. TLS برای Compose محلی غیرفعال است؛ در staging و production باید تنظیمات TLS همان محیط استفاده شود.

PostgreSQL در Compose فقط روی `127.0.0.1:${DB_HOST_PORT}` منتشر شده و از شبکه خارجی قابل دسترسی نیست.

## Entityها

- `users`: حساب کاربر؛ `phone` یکتا و تنها entity دارای `deleted_at` برای soft delete.
- `roles`: نقش‌های سیستمی و قابل تخصیص.
- `permissions`: مجوزهای مستقل با کلید یکتا و ماژول مربوطه.
- `user_roles`: ارتباط چندبه‌چند کاربران و نقش‌ها با کلید اصلی مرکب.
- `role_permissions`: ارتباط چندبه‌چند نقش‌ها و مجوزها با کلید اصلی مرکب.
- `addresses`: آدرس‌های متعلق به کاربر؛ هر کاربر حداکثر یک آدرس پیش‌فرض دارد.
- `audit_logs`: رخدادهای مدیریتی و حساس؛ حذف ردیف‌ها توسط trigger دیتابیس ممنوع است.
- `app_settings`: تنظیمات JSON برنامه با کلید یکتا.
- `alembic_version`: revision فعلی schema که Alembic مدیریت می‌کند.

## ERD متنی

```text
users 1 ────< addresses
  │
  ├────< user_roles >──── roles
  │                         │
  │                         └────< role_permissions >──── permissions
  │
  └────< audit_logs (actor_user_id nullable, ON DELETE SET NULL)

app_settings (مستقل)
```

## Queryهای بررسی

```sql
-- نسخه PostgreSQL، دیتابیس و timezone نشست
SELECT version(), current_database(), current_setting('TimeZone');

-- revision فعلی Alembic
SELECT version_num FROM alembic_version;

-- فهرست جدول‌های application
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- نقش‌های seedشده؛ باید دقیقاً پنج ردیف باشند
SELECT id, name, is_system
FROM roles
ORDER BY name;

-- constraintها و نوع آن‌ها
SELECT conrelid::regclass AS table_name, conname, contype
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY table_name::text, conname;

-- indexها
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- آدرس‌های پیش‌فرض تکراری؛ باید بدون ردیف باشد
SELECT user_id, count(*)
FROM addresses
WHERE is_default
GROUP BY user_id
HAVING count(*) > 1;

-- آخرین audit logها؛ فقط خواندنی بررسی شوند
SELECT id, actor_user_id, action, entity_type, entity_id, created_at
FROM audit_logs
ORDER BY created_at DESC
LIMIT 50;
```

## Migration و seed

```powershell
alembic upgrade head
alembic current
python -m app.db.seed
```

`python -m app.db.seed` از upsert استفاده می‌کند و اجرای چندباره آن نقش تکراری ایجاد نمی‌کند.
