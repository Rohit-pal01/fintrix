-- Init script for PostgreSQL with roles and database
CREATE EXTENSION IF NOT EXISTS vector;

\i /docker-entrypoint-initdb.d/schema.sql

-- Create read-only role if not exists
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'copilot_ro') THEN
      CREATE ROLE copilot_ro WITH LOGIN PASSWORD 'copilot_ro_pass';
   END IF;
END
$do$;

-- Grant connect and schema usage
GRANT CONNECT ON DATABASE finance_copilot TO copilot_ro;
GRANT USAGE ON SCHEMA public TO copilot_ro;

-- Grant SELECT only on user financial tables (Read-Only Safety)
GRANT SELECT ON users, accounts, categories, transactions, budgets, bills, goals TO copilot_ro;
-- Explicitly revoke write permissions
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON users, accounts, categories, transactions, budgets, bills, goals FROM copilot_ro;
