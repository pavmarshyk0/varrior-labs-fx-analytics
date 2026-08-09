# Calendar snapshots

Store immutable scheduled-event snapshots here. Required fields are
`snapshot_id`, UTC `as_of`, `source`, and sorted event records containing
`event_id`, `event_code`, `name`, `currency` (EUR or USD), UTC `scheduled_at`,
and `impact` (LOW/MEDIUM/HIGH). Revised/actual values and unknown fields are
rejected, so they cannot leak into historical decisions.
