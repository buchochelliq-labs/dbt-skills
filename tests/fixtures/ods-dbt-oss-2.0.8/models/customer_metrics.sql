select
    customer_id,
    length(normalized_name) as normalized_name_length
from {{ ref('customer_summary') }}
