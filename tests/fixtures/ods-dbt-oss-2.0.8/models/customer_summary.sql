select
    customer_id,
    customer_name,
    upper(customer_name) as normalized_name
from {{ ref('base_customers') }}
