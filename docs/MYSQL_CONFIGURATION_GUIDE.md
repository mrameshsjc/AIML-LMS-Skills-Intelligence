# MySQL Configuration Guide

How the engine stores its data today, and how MySQL is set up for it when it runs next to the enterprise LMS.

> **Current state:** the engine reads its LMS data from **CSV files** or **SQLite** (`DATA_SOURCE=csv|database`, Phase 9). SQLite needs no server, which keeps the local setup, Docker, Kubernetes and the free public demo simple. **MySQL is the production database for the LMS integration:** this guide describes that setup. The SQLite code was written so the switch is contained, as described in section 4.

---

## 1. Why the data layer is ready for MySQL

| Already in place | Effect for MySQL |
| --- | --- |
| **Repository interface** `app/repositories/base.py` (`LmsRepository`) with `CsvLmsRepository` and `SqliteLmsRepository` | A `MysqlLmsRepository` is one more class; services and APIs don't change |
| **Plain SQL with numbered migrations** (`app/database/migrations/0001_create_lms_tables.sql`, `schema_migrations` table) | The same tables and constraints are written in MySQL syntax |
| **Parity tests**: CSV and SQLite must give identical answers for all 100 employees | The same tests prove a MySQL repository correct |
| **`DATABASE_URL` setting** (a SecretStr-safe URL in `.env` / secrets) | Becomes `mysql+pymysql://user:password@host:3306/lms_ai` |
| **Start step** loads the sample data into an empty database | Works the same way with MySQL |

## 2. Database and user

On the MySQL server (8.0 or newer), as an administrator:

```sql
CREATE DATABASE lms_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'lms_ai'@'%' IDENTIFIED BY '<strong password from a password manager>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON lms_ai.* TO 'lms_ai'@'%';
FLUSH PRIVILEGES;
```

The engine only **reads** LMS data at runtime. In the LMS integration, give it a read-only user on the LMS's own tables (`GRANT SELECT`) or on views that expose only the needed columns, never e-mail addresses or other personal data it doesn't use.

## 3. Tables (MySQL syntax)

The eleven datasets map one-to-one to tables (columns: `DATA_DICTIONARY.md`). Example for two of them:

```sql
CREATE TABLE employees (
    employee_id        VARCHAR(10)  PRIMARY KEY,
    first_name         VARCHAR(100) NOT NULL,
    last_name          VARCHAR(100) NOT NULL,
    email              VARCHAR(255) NOT NULL UNIQUE,
    department         VARCHAR(100) NOT NULL,
    current_role_id    VARCHAR(10)  NOT NULL,
    manager_id         VARCHAR(10),
    hire_date          DATE         NOT NULL,
    location           VARCHAR(100),
    employment_status  VARCHAR(20)  NOT NULL,
    CONSTRAINT fk_emp_role    FOREIGN KEY (current_role_id) REFERENCES job_roles(role_id),
    CONSTRAINT fk_emp_manager FOREIGN KEY (manager_id)      REFERENCES employees(employee_id)
) ENGINE=InnoDB;

CREATE TABLE employee_skills (
    employee_id    VARCHAR(10) NOT NULL,
    skill_id       VARCHAR(10) NOT NULL,
    current_level  TINYINT     NOT NULL CHECK (current_level BETWEEN 0 AND 5),
    source         VARCHAR(30) NOT NULL,
    assessed_date  DATE,
    PRIMARY KEY (employee_id, skill_id),
    CONSTRAINT fk_es_emp   FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    CONSTRAINT fk_es_skill FOREIGN KEY (skill_id)    REFERENCES skills(skill_id)
) ENGINE=InnoDB;
```

Differences from the SQLite migration: `VARCHAR` lengths, `TINYINT`/`DECIMAL` types, `ENGINE=InnoDB` (foreign keys), and `utf8mb4` for names with any characters.

## 4. Connecting the engine

| Step | What changes |
| --- | --- |
| Driver | Add `pymysql` (or `mysqlclient`) to `requirements.txt` |
| Connection | `app/database/connection.py`: accept `mysql+pymysql://…` URLs next to `sqlite:///…` |
| Repository | `MysqlLmsRepository` with the same queries as `SqliteLmsRepository` (`%s` placeholders instead of `?`) |
| Choice | `DATA_SOURCE=database` + a MySQL `DATABASE_URL` selects it, in `app/api/dependencies.py` |
| Tests | Run the CSV/SQLite parity tests against a MySQL test database (e.g. a MySQL service container in CI) |

Settings (`.env`, Docker/Kubernetes secrets; never in Git):

```
DATA_SOURCE=database
DATABASE_URL=mysql+pymysql://lms_ai:<password>@mysql-host:3306/lms_ai?charset=utf8mb4
```

## 5. MySQL with Docker Compose

```yaml
services:
  mysql:
    image: mysql:8.4
    environment:
      MYSQL_DATABASE: lms_ai
      MYSQL_USER: lms_ai
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?set MYSQL_PASSWORD in .env}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD in .env}
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1"]
      interval: 10s
      retries: 10
  api:
    environment:
      DATA_SOURCE: database
      DATABASE_URL: mysql+pymysql://lms_ai:${MYSQL_PASSWORD}@mysql:3306/lms_ai?charset=utf8mb4
    depends_on:
      mysql:
        condition: service_healthy
volumes:
  mysql_data:
```

No port is published for MySQL: only containers on the Compose network reach it.

## 6. MySQL with Kubernetes

Use a managed MySQL (Azure Database for MySQL, Amazon RDS, Cloud SQL) or a StatefulSet with a PersistentVolumeClaim. The `DATABASE_URL` goes into the Secret `lms-secrets`, not the ConfigMap. With MySQL, the API's shared `ReadWriteOnce` volume is needed only for the index and models, so the API can scale across several nodes.

## 7. Security checklist

- [ ] Strong password from a password manager, stored only in secrets
- [ ] Read-only user for the engine on the LMS's tables or views
- [ ] TLS between the engine and MySQL outside a private network (`ssl_ca` in the URL options)
- [ ] No MySQL port exposed to the internet
- [ ] Backups and a tested restore for the engine's own tables (model metadata, accounts if stored there)
- [ ] Only the columns the engine needs; no personal data beyond what the APIs use
