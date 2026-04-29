WITH state_transitions_base AS (
  SELECT
    st.id,
    st.entity_type,
    st.entity_id,
    st.event_id,
    st.from_state,
    st.to_state,
    st.snapshot:vertical::STRING                        AS vertical,
    st.snapshot:renewalOverdueCycleEndDate::STRING       AS renewal_overdue_cycle_end_date,
    st.snapshot:renewalOverdueCycleStartDate::STRING     AS renewal_overdue_cycle_start_date,
    st.snapshot:tenureEndDate::STRING                    AS tenure_end_date,
    st.snapshot:tenureStartDate::STRING                  AS tenure_start_date,
    st.snapshot:tenureInMonths::INT                      AS tenure_in_months,
    st.snapshot:pickupDate::STRING                       AS pickup_date,
    st.snapshot:activationDate::STRING                   AS activation_date,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPreTax::DOUBLE AS pre_tax_amout,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPostTax::DOUBLE AS amount_paid,
    st.created_at + interval '330 minutes'               AS transition_created_at
  FROM furlenco_silver.order_management_systems_evolve.state_transitions st
  WHERE st.snapshot:vertical::STRING = 'FURLENCO_RENTAL'
  -- AND st.created_at + interval '330 minutes' >= '2025-01-01'
  AND st.entity_id = :entity_id
  -- 1342500
  AND st.entity_type = lower(:entity_type)
  AND st.snapshot:activationDate::STRING is not null
),
-- Join with events and calculate effective tenure
with_effective_tenure AS (
  SELECT
    st.id AS state_transition_id,
    st.entity_type,
    st.entity_id,
    st.from_state,
    st.to_state,
    st.renewal_overdue_cycle_start_date,
    st.renewal_overdue_cycle_end_date,
    st.tenure_start_date,
    st.tenure_end_date,
    st.tenure_in_months,
    COALESCE(st.renewal_overdue_cycle_start_date, st.tenure_start_date) AS effective_tenure_start,
    COALESCE(st.renewal_overdue_cycle_end_date, st.tenure_end_date) AS effective_tenure_end,
    st.pickup_date,
    st.activation_date,
    st.pre_tax_amout,
    st.amount_paid,
    st.transition_created_at,
    ev.id AS event_id,
    ev.name AS event_name
  FROM state_transitions_base st
  INNER JOIN furlenco_silver.order_management_systems_evolve.events ev
    ON st.event_id = ev.id
  WHERE ev.name IN ('ORDER_SHIPMENT_DELIVERED','ORDER_FULFILLMENT_FULFILLED','RENEWAL_OVERDUE','RENEWAL_APPLIED','RENT_TO_PURCHASE_ORDER_PAYMENT_SUCCEEDED','OUTSTANDING_PAYMENT_RECEIVED','SWAP_SHIPMENT_DELIVERED')
),
-- Deduplicate renewal events: prefer RENEWAL_APPLIED over RENEWAL_OVERDUE for same cycle
renewal_events_ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY entity_id, effective_tenure_start, effective_tenure_end
      ORDER BY CASE event_name 
        WHEN 'RENEWAL_APPLIED' THEN 1 
        WHEN 'RENEWAL_OVERDUE' THEN 2 
      END
    ) AS rnk
  FROM with_effective_tenure
  WHERE event_name IN ('RENEWAL_OVERDUE', 'RENEWAL_APPLIED')
),
-- Other events: no deduplication needed
other_events AS (
  SELECT *, 1 AS rnk
  FROM with_effective_tenure
  WHERE event_name NOT IN ('RENEWAL_OVERDUE', 'RENEWAL_APPLIED')
),
-- Combine: deduplicated renewals + other events
combined AS (
  SELECT * FROM renewal_events_ranked WHERE rnk = 1
  UNION ALL
  SELECT * FROM other_events
)
SELECT
  state_transition_id,
  entity_type,
  entity_id,
  from_state,
  to_state,
  effective_tenure_start as tenure_start_date,
  effective_tenure_end as tenure_end_date,
  tenure_in_months,
  pickup_date,
  activation_date,
  pre_tax_amout,
  amount_paid,
  transition_created_at,
  event_id,
  event_name
FROM combined
ORDER BY state_transition_id

