#!/usr/bin/env bash
# 建立本地開發用的資料庫與三個最小權限帳號。可重複執行(idempotent)。
#
#   sudo db/scripts/bootstrap_local.sh
#
# 密碼可用環境變數覆寫;不覆寫就用下面的本地預設值(只適用本機開發,
# 正式環境的密碼走 secret manager,不寫在腳本裡)。
set -euo pipefail

DB_NAME="${DB_NAME:-pet_camera}"
PW_MIGRATE="${PW_MIGRATE:-migrate_local_pw}"
PW_APP="${PW_APP:-app_local_pw}"
PW_READONLY="${PW_READONLY:-readonly_local_pw}"
OS_USER="${SUDO_USER:-$(id -un)}"

if [[ "$(id -un)" != "postgres" ]]; then
    exec sudo -u postgres \
        DB_NAME="$DB_NAME" PW_MIGRATE="$PW_MIGRATE" PW_APP="$PW_APP" \
        PW_READONLY="$PW_READONLY" SUDO_USER="$OS_USER" \
        bash "$0" "$@"
fi

psql -v ON_ERROR_STOP=1 <<SQL
-- 三個帳號分別對應三種用途,誰也拿不到多餘的權限:
--   migrate  : 改 schema(只給 Alembic 用)
--   app      : 讀寫資料,不能改 schema(七個微服務用)
--   readonly : 只讀(分析、報表、手動查詢)
do \$\$
begin
    if not exists (select 1 from pg_roles where rolname = 'pet_camera_migrate') then
        create role pet_camera_migrate login password '${PW_MIGRATE}';
    else
        alter role pet_camera_migrate login password '${PW_MIGRATE}';
    end if;
    if not exists (select 1 from pg_roles where rolname = 'pet_camera_app') then
        create role pet_camera_app login password '${PW_APP}';
    else
        alter role pet_camera_app login password '${PW_APP}';
    end if;
    if not exists (select 1 from pg_roles where rolname = 'pet_camera_readonly') then
        create role pet_camera_readonly login password '${PW_READONLY}';
    else
        alter role pet_camera_readonly login password '${PW_READONLY}';
    end if;
    -- 本機方便用:讓目前的 OS 使用者可以直接 psql 進這個資料庫
    if not exists (select 1 from pg_roles where rolname = '${OS_USER}') then
        create role ${OS_USER} login superuser;
    end if;
end
\$\$;
SQL

if ! psql -tAc "select 1 from pg_database where datname = '${DB_NAME}'" | grep -q 1; then
    createdb -O pet_camera_migrate "${DB_NAME}"
    echo "已建立資料庫 ${DB_NAME}"
else
    echo "資料庫 ${DB_NAME} 已存在,略過建立"
fi

psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<SQL
-- 不讓任何人隨便在 public schema 建表
revoke create on schema public from public;
grant usage on schema public to pet_camera_app, pet_camera_readonly;
grant create, usage on schema public to pet_camera_migrate;

-- 已存在的表(重跑時)
grant select, insert, update, delete on all tables in schema public to pet_camera_app;
grant select on all tables in schema public to pet_camera_readonly;

-- 未來由 migrate 帳號建立的表,自動帶上這些權限,不必每次 migration 後手動 grant
alter default privileges for role pet_camera_migrate in schema public
    grant select, insert, update, delete on tables to pet_camera_app;
alter default privileges for role pet_camera_migrate in schema public
    grant select on tables to pet_camera_readonly;
alter default privileges for role pet_camera_migrate in schema public
    grant usage, select on sequences to pet_camera_app;
SQL

echo "完成:資料庫 ${DB_NAME} 與 migrate / app / readonly 三個帳號已就緒。"
echo "下一步:cd db && cp .env.example .env && set -a && . ./.env && set +a && uv run alembic upgrade head"
