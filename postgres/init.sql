-- Una sola instancia de PostgreSQL, pero Database per Service a nivel lógico:
-- cada servicio tiene su esquema y su usuario, y no puede leer los de los demás.
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE USER flota_user    WITH PASSWORD 'flota_pw';
CREATE USER despacho_user WITH PASSWORD 'despacho_pw';
CREATE USER reportes_user WITH PASSWORD 'reportes_pw';

CREATE SCHEMA flota    AUTHORIZATION flota_user;
CREATE SCHEMA despacho AUTHORIZATION despacho_user;
CREATE SCHEMA reportes AUTHORIZATION reportes_user;

REVOKE ALL ON DATABASE ambulancias FROM PUBLIC;
GRANT CONNECT ON DATABASE ambulancias TO flota_user, despacho_user, reportes_user;
