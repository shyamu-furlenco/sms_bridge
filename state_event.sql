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
    st.snapshot:pickupDate::STRING                       AS pickup_date,
    st.snapshot:activationDate::STRING                   AS activation_date,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPreTax::DOUBLE AS pre_tax_amout,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPostTax::DOUBLE AS amount_paid,
    st.created_at + interval '330 minutes'               AS transition_created_at
  FROM furlenco_silver.order_management_systems_evolve.state_transitions st
  WHERE st.snapshot:vertical::STRING = 'FURLENCO_RENTAL'
  -- AND st.created_at + interval '330 minutes' >= '2025-01-01'
  AND st.entity_id = 1342500
  AND st.entity_type = 'ITEM'
)

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
WHERE ev.name in ('ORDER_SHIPMENT_DELIVERED','RENEWAL_OVERDUE','RENEWAL_APPLIED','RENT_TO_PURCHASE_ORDER_PAYMENT_SUCCEEDED','OUTSTANDING_PAYMENT_RECEIVED')
ORDER BY state_transition_id