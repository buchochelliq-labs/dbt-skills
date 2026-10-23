-- Original Northwind-style synthetic fixture, not a copy of Microsoft's sample.
PRAGMA foreign_keys = ON;
CREATE TABLE categories (
 category_id INTEGER PRIMARY KEY, category_name TEXT NOT NULL UNIQUE
);
CREATE TABLE suppliers (
 supplier_id INTEGER PRIMARY KEY, company_name TEXT NOT NULL, country_code TEXT NOT NULL
);
CREATE TABLE products (
 product_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL,
 supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id),
 category_id INTEGER NOT NULL REFERENCES categories(category_id),
 unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
 discontinued INTEGER NOT NULL DEFAULT 0 CHECK(discontinued IN (0,1))
);
CREATE TABLE customers (
 customer_id INTEGER PRIMARY KEY, company_name TEXT NOT NULL, country_code TEXT NOT NULL
);
CREATE TABLE employees (
 employee_id INTEGER PRIMARY KEY, display_name TEXT NOT NULL,
 manager_id INTEGER REFERENCES employees(employee_id), CHECK(manager_id IS NULL OR manager_id <> employee_id)
);
CREATE TABLE shippers (
 shipper_id INTEGER PRIMARY KEY, company_name TEXT NOT NULL
);
CREATE TABLE orders (
 order_id INTEGER PRIMARY KEY,
 customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
 employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
 shipper_id INTEGER NOT NULL REFERENCES shippers(shipper_id),
 order_date TEXT NOT NULL, shipped_date TEXT,
 status TEXT NOT NULL CHECK(status IN ('pending','shipped','cancelled')),
 freight_cents INTEGER NOT NULL CHECK(freight_cents >= 0),
 CHECK(shipped_date IS NULL OR shipped_date >= order_date)
);
CREATE TABLE order_details (
 order_id INTEGER NOT NULL REFERENCES orders(order_id),
 line_number INTEGER NOT NULL CHECK(line_number > 0),
 product_id INTEGER NOT NULL REFERENCES products(product_id),
 quantity INTEGER NOT NULL CHECK(quantity > 0),
 unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
 discount_bps INTEGER NOT NULL CHECK(discount_bps BETWEEN 0 AND 10000),
 PRIMARY KEY(order_id,line_number)
);
CREATE INDEX orders_customer ON orders(customer_id);
CREATE INDEX orders_employee ON orders(employee_id);
CREATE INDEX orders_shipper ON orders(shipper_id);
CREATE INDEX details_product ON order_details(product_id);
CREATE INDEX products_supplier ON products(supplier_id);
CREATE INDEX products_category ON products(category_id);
CREATE INDEX employees_manager ON employees(manager_id);
