
  SELECT
    it.id, it.name, it.state, it.activation_date,
    tenure_start_date, tenure_end_date, 
    coalesce(pickup_date,rto.created_at + interval '330 minutes') as pickup_date,
    user_id, tenure_in_months,
    renewal_overdue_cycle_start_date, renewal_overdue_cycle_end_date,
    it.payment_details:payableAfterPaymentOffers:byCashPreTax,
    current_date as current_date,
    add_months(DATE_TRUNC('month',current_date),1) as next_month_start_date,
    it.vertical
  FROM furlenco_silver.order_management_systems_evolve.items it
  LEFT JOIN furlenco_silver.order_management_systems_evolve.rent_to_purchase_items rtp
  ON it.id = rtp.item_id 
  LEFT JOIN furlenco_silver.order_management_systems_evolve.rent_to_purchase_orders as rto
  ON rto.id = rtp.rent_to_purchase_order_id
  WHERE it.vertical = 'FURLENCO_RENTAL'
  AND it.state in ('ACTIVE','AWAITING_RENEWAL_PAYMENT','RENEWAL_OVERDUE', 
  'RENT_TO_PURCHASE_IN_PROGRESS','OUT_FOR_PICKUP','PICKUP_SCHEDULED','PICKUP_TO_BE_SCHEDULED',
   'REPLACEMENT_IN_PROGRESS','SETTLEMENT_IN_PROGRESS','SWAP_IN_PROGRESS',
   'SWAPPED','PICKED_UP','PURCHASED'
   )
   AND (coalesce(pickup_date,rto.created_at + interval '330 minutes') is null 
   or coalesce(pickup_date,rto.created_at + interval '330 minutes') >= add_months(DATE_TRUNC('month',current_date),1))
  -- AND it.id = 28470

