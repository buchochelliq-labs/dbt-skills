select *
from {{ source('external', 'raw_events') }}
