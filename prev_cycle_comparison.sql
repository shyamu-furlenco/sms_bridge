WITH base AS (
  SELECT
    it.id, it.name, it.state, it.activation_date,
    it.tenure_start_date, it.tenure_end_date,
    COALESCE(it.pickup_date, rto.created_at + interval '330 minutes') AS pickup_date,
    it.user_id, it.tenure_in_months,
    it.renewal_overdue_cycle_start_date, it.renewal_overdue_cycle_end_date,
    CASE WHEN it.state = 'RENEWAL_OVERDUE'
      THEN it.Current_Pricing_Details:basePrice::DOUBLE
      ELSE it.payment_details:payableAfterPaymentOffers:byCashPreTax::DOUBLE
    END AS pre_tax_amount,
    current_date AS current_date,
    it.vertical,
    COALESCE(it.renewal_overdue_cycle_start_date, it.tenure_start_date) AS current_effective_start,
    COALESCE(it.renewal_overdue_cycle_end_date,   it.tenure_end_date)   AS current_effective_end
  FROM furlenco_silver.order_management_systems_evolve.items it
  LEFT JOIN furlenco_silver.order_management_systems_evolve.rent_to_purchase_items rtp
    ON it.id = rtp.item_id
  LEFT JOIN furlenco_silver.order_management_systems_evolve.rent_to_purchase_orders AS rto
    ON rto.id = rtp.rent_to_purchase_order_id AND rto.state <> 'CANCELLED'
  WHERE it.vertical = 'FURLENCO_RENTAL'
  AND it.state IN (
    'ACTIVE','AWAITING_RENEWAL_PAYMENT','RENEWAL_OVERDUE',
    'RENT_TO_PURCHASE_IN_PROGRESS','OUT_FOR_PICKUP','PICKUP_SCHEDULED','PICKUP_TO_BE_SCHEDULED',
    'REPLACEMENT_IN_PROGRESS','SETTLEMENT_IN_PROGRESS','SWAP_IN_PROGRESS',
    'SWAPPED','PICKED_UP','PURCHASED'
  )
  AND (
    COALESCE(it.pickup_date, rto.created_at + interval '330 minutes') IS NULL
    OR COALESCE(it.pickup_date, rto.created_at + interval '330 minutes') >= add_months(DATE_TRUNC('month', current_date), 1)
  )
  AND it.id = :entity_id  -- uncomment for single-item testing
  -- [Fix 1] Collapse multiple RTP orders per item — pick latest to avoid fan-out
  QUALIFY ROW_NUMBER() OVER (PARTITION BY it.id ORDER BY rtp.id DESC NULLS LAST) = 1
),

-- [OPT 1] Push events JOIN + name filter here — fewer rows flow into all downstream CTEs
state_transitions_base AS (
  SELECT
    st.id, st.entity_type, st.entity_id, st.from_state, st.to_state,
    CAST(st.snapshot:renewalOverdueCycleEndDate   AS DATE) AS renewal_overdue_cycle_end_date,
    CAST(st.snapshot:renewalOverdueCycleStartDate AS DATE) AS renewal_overdue_cycle_start_date,
    CAST(st.snapshot:tenureEndDate                AS DATE) AS tenure_end_date,
    CAST(st.snapshot:tenureStartDate              AS DATE) AS tenure_start_date,
    st.snapshot:tenureInMonths::INT                        AS tenure_in_months,
    st.snapshot:pickupDate::STRING                         AS pickup_date,
    st.snapshot:activationDate::STRING                     AS activation_date,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPreTax::DOUBLE  AS pre_tax_amount,
    st.snapshot:paymentDetails.payableAfterPaymentOffers.byCashPostTax::DOUBLE AS amount_paid,
    st.snapshot:currentPricingDetails:basePrice::DOUBLE                        AS base_price,
    st.created_at + interval '330 minutes'                 AS transition_created_at,
    ev.name                                                AS event_name
  FROM furlenco_silver.order_management_systems_evolve.state_transitions st
  INNER JOIN furlenco_silver.order_management_systems_evolve.events ev
    ON st.event_id = ev.id
   AND ev.name IN (
      'ORDER_SHIPMENT_DELIVERED','ORDER_FULFILLMENT_FULFILLED',
      'RENEWAL_OVERDUE','RENEWAL_APPLIED',
      'RENT_TO_PURCHASE_ORDER_PAYMENT_SUCCEEDED','OUTSTANDING_PAYMENT_RECEIVED',
      'SWAP_SHIPMENT_DELIVERED'
    )
  -- [OPT 4] Cheap non-JSON filters first to skip JSON parsing on non-matching rows
  WHERE st.entity_type = 'ITEM'
  AND st.entity_id IN (SELECT id FROM base)
  AND st.snapshot:vertical::STRING = 'FURLENCO_RENTAL'
  AND st.snapshot:activationDate::STRING IS NOT NULL
  AND st.entity_id = :entity_id  -- uncomment for single-item testing
),

with_effective_tenure AS (
  SELECT
    st.id AS state_transition_id,
    st.entity_type, st.entity_id, st.from_state, st.to_state,
    st.renewal_overdue_cycle_start_date, st.renewal_overdue_cycle_end_date,
    st.tenure_start_date, st.tenure_end_date, st.tenure_in_months,
    COALESCE(st.renewal_overdue_cycle_start_date, st.tenure_start_date) AS effective_tenure_start,
    COALESCE(st.renewal_overdue_cycle_end_date,   st.tenure_end_date)   AS effective_tenure_end,
    st.pickup_date, st.activation_date, st.amount_paid,
    -- [Fix 2] RENEWAL_OVERDUE uses basePrice; COALESCE guards against older snapshots missing the field
    CASE WHEN st.event_name = 'RENEWAL_OVERDUE'
      THEN COALESCE(st.base_price, st.pre_tax_amount)
      ELSE st.pre_tax_amount
    END AS pre_tax_amount,
    st.transition_created_at,
    st.event_name  -- already resolved in state_transitions_base, no JOIN needed here
  FROM state_transitions_base st
),

-- [OPT 2] renewal_events_ranked + other_events + combined_state_history removed.
-- previous_cycle's ORDER BY already picks RENEWAL_APPLIED > RENEWAL_OVERDUE > delivery
-- for the same cycle window, so the intermediate dedup was redundant.
previous_cycle AS (
  SELECT
    sh.*,
    ROW_NUMBER() OVER (
      PARTITION BY sh.entity_id
      ORDER BY
        sh.effective_tenure_end DESC,
        CASE sh.event_name
          WHEN 'RENEWAL_APPLIED'             THEN 1
          WHEN 'RENEWAL_OVERDUE'             THEN 2
          WHEN 'ORDER_SHIPMENT_DELIVERED'    THEN 3
          WHEN 'ORDER_FULFILLMENT_FULFILLED' THEN 3
          ELSE 9
        END,
        sh.transition_created_at DESC,
        sh.state_transition_id DESC
    ) AS prev_rn
  FROM with_effective_tenure sh
  -- [OPT 3] base.id is already unique after QUALIFY — DISTINCT removed
  INNER JOIN base b ON sh.entity_id = b.id
  -- Furlenco cycle convention: end date = day before next start (e.g. Apr 7 → Apr 8),
  -- so strict < correctly excludes the current cycle without needing <=
  WHERE sh.effective_tenure_end < b.current_effective_start
)

SELECT
  b.id, b.name, b.state, b.activation_date, b.user_id, b.verticala,
  -- Current billing cycle
  b.current_effective_start                  AS current_tenure_start,
  b.current_effective_end                    AS current_tenure_end,
  b.tenure_in_months                         AS current_tenure_months,
  b.pre_tax_amount,
  -- Previous billing cycle
  pc.effective_tenure_start                  AS prev_tenure_start,
  pc.effective_tenure_end                    AS prev_tenure_end,
  pc.tenure_in_months                        AS prev_tenure_months,
  pc.pre_tax_amount                          AS prev_pre_tax_amount
FROM base b
LEFT JOIN previous_cycle pc ON pc.entity_id = b.id AND pc.prev_rn = 1
ORDER BY b.id
