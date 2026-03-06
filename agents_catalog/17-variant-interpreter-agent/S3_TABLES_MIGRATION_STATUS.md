# S3 Tables Migration - Key Changes Summary

## Updated Configuration
- Database: `variant_db` (was: LAKE_FORMATION_DATABASE)
- Catalog: `s3tables::genomics-variant-tables`
- Table: `genomic_variants`
- Output: `s3://genomics-vep-output-{ACCOUNT_ID}-{ACCOUNT_ID}-{REGION}/athena-results/`

## Schema Mapping
| Variant Store | S3 Tables |
|--------------|-----------|
| sampleid | sample_name |
| contigname | chrom |
| start | pos |
| referenceallele | ref |
| alternatealleles[1] | alt[1] |
| filters | filter |
| info['DP'] | info['DP'] |

## Functions Updated
1. ✅ execute_athena_query_on_stores() - Added S3 Tables catalog
2. ✅ get_available_samples_from_variant_store() - Updated to query genomic_variants

## Functions Needing Update
- analyze_variants_by_gene() - Complex VEP/ClinVar queries need simplification
- All other variant analysis functions using old schema

## Test Query
```sql
SELECT sample_name, COUNT(*) as variant_count
FROM genomic_variants
GROUP BY sample_name
```

## Next Steps
1. Test basic queries work
2. Update remaining analysis functions
3. Add VEP annotation support later
