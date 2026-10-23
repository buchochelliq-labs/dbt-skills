-- Illustrative draft: grain and source mapping require human confirmation.
select
    customer_id,
    customer_name,
    updated_at
from {{ source('xyz', 'customers') }}
