# Databricks notebook source
# MAGIC %md
# MAGIC ## Feb vs March Noida Snapshot: Entity Comparison (PySpark)
# MAGIC Tables: `furlenco_analytics.user_defined_tables.feb_snapshot_noida` and `march_snapshot_noida`

# COMMAND ----------

# CELL 1: Load tables and summary counts
from pyspark.sql import functions as F

feb = spark.table("furlenco_analytics.user_defined_tables.feb_snapshot_noida")
mar = spark.table("furlenco_analytics.user_defined_tables.march_snapshot_noida")

feb_ids = feb.select("entity_id").distinct()
mar_ids = mar.select("entity_id").distinct()

feb_total  = feb_ids.count()
mar_total  = mar_ids.count()
common     = feb_ids.join(mar_ids, "entity_id", "inner").count()
feb_only_n = feb_ids.join(mar_ids, "entity_id", "left_anti").count()
mar_only_n = mar_ids.join(feb_ids, "entity_id", "left_anti").count()

summary = spark.createDataFrame(
    [(feb_total, mar_total, common, feb_only_n, mar_only_n)],
    ["feb_total", "mar_total", "common_both", "feb_only", "mar_only"]
)
display(summary)

# COMMAND ----------

# CELL 2: Feb-Only Entities (present in Feb, NOT in March — churned)
feb_only_df = (
    feb
    .join(mar_ids, "entity_id", "left_anti")
    .orderBy("entity_id")
)
display(feb_only_df)

# COMMAND ----------

# CELL 3: March-Only Entities (present in March, NOT in Feb — new activations)
mar_only_df = (
    mar
    .join(feb_ids, "entity_id", "left_anti")
    .orderBy("entity_id")
)
display(mar_only_df)

# COMMAND ----------

# CELL 4: Common Entities — Feb and March values side by side
feb_renamed = feb.select(
    F.col("entity_id"),
    *[F.col(c).alias(f"feb_{c}") for c in feb.columns if c != "entity_id"]
)
mar_renamed = mar.select(
    F.col("entity_id"),
    *[F.col(c).alias(f"mar_{c}") for c in mar.columns if c != "entity_id"]
)

common_df = (
    feb_renamed
    .join(mar_renamed, "entity_id", "inner")
    .orderBy("entity_id")
)
display(common_df)

# COMMAND ----------

# CELL 5: Aggregate by entity — handles multiple cycles per entity per month
# (e.g. entity with cycle ending Feb 19 AND cycle starting Feb 20 both appear in feb_snapshot)
feb_agg = (
    feb
    .groupBy("entity_id")
    .agg(
        F.round(F.sum("realised_revenue"), 2).alias("realised_revenue"),
        F.round(F.sum("cycle_amount"), 2).alias("cycle_amount"),
        F.count("*").alias("cycle_count"),
        F.max("cycle_num").alias("max_cycle_num"),
        F.sum("days").alias("total_days"),
        F.collect_set("period_type").alias("period_types"),
        F.min("activation_date").alias("activation_date"),
        F.max("pickup_date").alias("pickup_date"),
    )
)

mar_agg = (
    mar
    .groupBy("entity_id")
    .agg(
        F.round(F.sum("realised_revenue"), 2).alias("realised_revenue"),
        F.round(F.sum("cycle_amount"), 2).alias("cycle_amount"),
        F.count("*").alias("cycle_count"),
        F.max("cycle_num").alias("max_cycle_num"),
        F.sum("days").alias("total_days"),
        F.collect_set("period_type").alias("period_types"),
        F.min("activation_date").alias("activation_date"),
        F.max("pickup_date").alias("pickup_date"),
    )
)

feb_agg_ids = feb_agg.select("entity_id")
mar_agg_ids = mar_agg.select("entity_id")

print(f"Unique Feb entities: {feb_agg_ids.count()}")
print(f"Unique Mar entities: {mar_agg_ids.count()}")

# COMMAND ----------

# CELL 6: Revenue bridge — 3-component decomposition
feb_total = feb.agg(F.round(F.sum("realised_revenue"), 2).alias("v")).collect()[0]["v"]
mar_total = mar.agg(F.round(F.sum("realised_revenue"), 2).alias("v")).collect()[0]["v"]
total_delta = round(mar_total - feb_total, 2)

churn_rev = (
    feb_agg.join(mar_agg_ids, "entity_id", "left_anti")
    .agg(F.round(F.sum("realised_revenue"), 2)).collect()[0][0]
) or 0.0

new_rev = (
    mar_agg.join(feb_agg_ids, "entity_id", "left_anti")
    .agg(F.round(F.sum("realised_revenue"), 2)).collect()[0][0]
) or 0.0

feb_common_rev = (
    feb_agg.join(mar_agg_ids, "entity_id", "inner")
    .agg(F.round(F.sum("realised_revenue"), 2)).collect()[0][0]
) or 0.0

mar_common_rev = (
    mar_agg.join(feb_agg_ids, "entity_id", "inner")
    .agg(F.round(F.sum("realised_revenue"), 2)).collect()[0][0]
) or 0.0

common_delta = round(mar_common_rev - feb_common_rev, 2)
explained    = round(-churn_rev + new_rev + common_delta, 2)
residual     = round(total_delta - explained, 2)

bridge_summary = spark.createDataFrame([
    ("Feb total realised revenue",           feb_total,      None,           None),
    ("Mar total realised revenue",           mar_total,      None,           None),
    ("Total delta (Mar - Feb)",              total_delta,    None,           None),
    ("Component 1: Churned (feb-only)",     -churn_rev,     churn_rev,      0.0),
    ("Component 2: New activations",         new_rev,        0.0,            new_rev),
    ("Component 3: Common entity delta",    common_delta,   feb_common_rev, mar_common_rev),
    ("Explained delta (sum of components)", explained,      None,           None),
    ("Residual (should be 0)",              residual,       None,           None),
], ["category", "delta_realised", "feb_realised", "mar_realised"])

display(bridge_summary)

# COMMAND ----------

# CELL 7: Common entity change classification
feb_r = feb_agg.select(
    "entity_id",
    F.col("realised_revenue").alias("feb_realised"),
    F.col("cycle_amount").alias("feb_cycle_amount"),
    F.col("cycle_count").alias("feb_cycle_count"),
    F.col("max_cycle_num").alias("feb_max_cycle_num"),
    F.col("total_days").alias("feb_days"),
    F.col("period_types").alias("feb_period_types"),
    F.col("activation_date").alias("feb_activation_date"),
    F.col("pickup_date").alias("feb_pickup_date"),
)

mar_r = mar_agg.select(
    "entity_id",
    F.col("realised_revenue").alias("mar_realised"),
    F.col("cycle_amount").alias("mar_cycle_amount"),
    F.col("cycle_count").alias("mar_cycle_count"),
    F.col("max_cycle_num").alias("mar_max_cycle_num"),
    F.col("total_days").alias("mar_days"),
    F.col("period_types").alias("mar_period_types"),
    F.col("activation_date").alias("mar_activation_date"),
    F.col("pickup_date").alias("mar_pickup_date"),
)

common_classified = (
    feb_r.join(mar_r, "entity_id", "inner")
    .withColumn("delta_realised",      F.round(F.col("mar_realised") - F.col("feb_realised"), 2))
    .withColumn("delta_cycle_amount",  F.round(F.col("mar_cycle_amount") - F.col("feb_cycle_amount"), 2))
    .withColumn("delta_days",          F.col("mar_days") - F.col("feb_days"))
    .withColumn("cycle_count_changed", F.col("mar_cycle_count") != F.col("feb_cycle_count"))
    .withColumn("period_type_shifted", F.col("mar_period_types") != F.col("feb_period_types"))
    .withColumn("change_driver",
        F.when(F.col("delta_realised") == 0,          "stable")
         .when(F.col("delta_cycle_amount") != 0,      "rate_change")       # upgrade / downgrade
         .when(F.col("period_type_shifted"),           "period_type_shift") # TENURE <-> PURE_OVERDUE
         .when(
             F.col("cycle_count_changed") | (F.col("delta_days") != 0),
             "partial_period"  # new activation / imminent return / mid-month renewal
         )
         .when(F.col("delta_realised") != 0,          "realised_only_change")
         .otherwise("other")
    )
    .withColumn("change_detail",
        F.when(F.col("change_driver") == "rate_change",
            F.when(F.col("delta_cycle_amount") > 0, "upgrade").otherwise("downgrade")
        )
        .when(F.col("change_driver") == "period_type_shift",
            F.concat(
                F.array_join(F.col("feb_period_types"), "+"),
                F.lit(" -> "),
                F.array_join(F.col("mar_period_types"), "+"),
            )
        )
        .otherwise(F.lit(None))
    )
)

display(common_classified.orderBy("change_driver", "entity_id"))

# COMMAND ----------

# CELL 8: Full bridge table — all buckets, entity count, revenue columns, % of delta
churned_summary = (
    feb_r.join(mar_agg_ids, "entity_id", "left_anti")
    .agg(
        F.count("entity_id").alias("entity_count"),
        F.round(F.sum("feb_realised"), 2).alias("feb_realised"),
        F.lit(0.0).alias("mar_realised"),
    )
    .withColumn("delta_realised", F.col("mar_realised") - F.col("feb_realised"))
    .withColumn("change_driver", F.lit("churned"))
    .withColumn("change_detail", F.lit(None))
)

new_summary = (
    mar_r.join(feb_agg_ids, "entity_id", "left_anti")
    .agg(
        F.count("entity_id").alias("entity_count"),
        F.lit(0.0).alias("feb_realised"),
        F.round(F.sum("mar_realised"), 2).alias("mar_realised"),
    )
    .withColumn("delta_realised", F.col("mar_realised") - F.col("feb_realised"))
    .withColumn("change_driver", F.lit("new_activation"))
    .withColumn("change_detail", F.lit(None))
)

common_summary = (
    common_classified
    .groupBy("change_driver", "change_detail")
    .agg(
        F.count("entity_id").alias("entity_count"),
        F.round(F.sum("feb_realised"), 2).alias("feb_realised"),
        F.round(F.sum("mar_realised"), 2).alias("mar_realised"),
        F.round(F.sum("delta_realised"), 2).alias("delta_realised"),
    )
)

bridge_detail = (
    churned_summary.select("change_driver", "change_detail", "entity_count", "feb_realised", "mar_realised", "delta_realised")
    .unionByName(new_summary.select("change_driver", "change_detail", "entity_count", "feb_realised", "mar_realised", "delta_realised"))
    .unionByName(common_summary)
    .withColumn("pct_of_total_delta", F.round(F.col("delta_realised") / F.lit(total_delta) * 100, 1))
    .orderBy(F.abs(F.col("delta_realised")).desc())
)

total_row = spark.createDataFrame(
    [("TOTAL", None, None, feb_total, mar_total, total_delta, 100.0)],
    ["change_driver", "change_detail", "entity_count", "feb_realised", "mar_realised", "delta_realised", "pct_of_total_delta"]
)

display(bridge_detail.unionByName(total_row, allowMissingColumns=True))

# COMMAND ----------

# CELL 9: Entity-level drilldown for each change bucket
DRIVERS = [
    "churned", "new_activation", "rate_change", "period_type_shift",
    "partial_period", "realised_only_change", "other",
]

for driver in DRIVERS:
    if driver == "churned":
        drilldown = (
            feb_r.join(mar_agg_ids, "entity_id", "left_anti")
            .withColumn("mar_realised", F.lit(0.0))
            .withColumn("delta_realised", -F.col("feb_realised"))
            .select(
                "entity_id", "feb_realised", "mar_realised", "delta_realised",
                "feb_cycle_amount", "feb_days", "feb_period_types",
                "feb_activation_date", "feb_pickup_date",
            )
            .orderBy(F.col("delta_realised").asc())
        )
    elif driver == "new_activation":
        drilldown = (
            mar_r.join(feb_agg_ids, "entity_id", "left_anti")
            .withColumn("feb_realised", F.lit(0.0))
            .withColumn("delta_realised", F.col("mar_realised"))
            .select(
                "entity_id", "feb_realised", "mar_realised", "delta_realised",
                "mar_cycle_amount", "mar_days", "mar_period_types",
                "mar_activation_date", "mar_pickup_date",
            )
            .orderBy(F.col("delta_realised").desc())
        )
    else:
        drilldown = (
            common_classified
            .filter(F.col("change_driver") == driver)
            .select(
                "entity_id", "feb_realised", "mar_realised", "delta_realised",
                "feb_cycle_amount", "mar_cycle_amount", "delta_cycle_amount",
                "feb_days", "mar_days", "delta_days",
                "feb_period_types", "mar_period_types",
                "feb_max_cycle_num", "mar_max_cycle_num",
                "feb_activation_date", "mar_activation_date",
                "feb_pickup_date", "mar_pickup_date",
                "change_detail",
            )
            .orderBy(F.col("delta_realised").asc())
        )

    count = drilldown.count()
    if count > 0:
        print(f"\n{'='*60}  {driver.upper()}  ({count} entities)  {'='*60}")
        display(drilldown)

# COMMAND ----------

# CELL 10: Sanity check — bridge must sum to total delta
bridge_check  = bridge_detail.agg(F.round(F.sum("delta_realised"), 2).alias("s")).collect()[0]["s"]
residual_final = round(total_delta - bridge_check, 2)

print(f"Total delta (Mar - Feb):          Rs{total_delta:>14,.2f}")
print(f"Sum of all bridge components:     Rs{bridge_check:>14,.2f}")
print(f"Residual (should be 0.00):        Rs{residual_final:>14,.2f}")
print()
if abs(residual_final) < 1.0:
    print("BRIDGE IS BALANCED -- 100% of delta is explained")
else:
    print(f"UNBALANCED -- Rs{residual_final:,.2f} unexplained. Check for join fan-out or missing categories.")
