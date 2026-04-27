\set ON_ERROR_STOP on

SELECT 'CREATE DATABASE travel_orders ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (
  SELECT 1
  FROM pg_database
  WHERE datname = 'travel_orders'
)\gexec
