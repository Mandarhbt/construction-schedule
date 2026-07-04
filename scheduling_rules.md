# Construction Scheduling Logic Rules
# ─────────────────────────────────────────────────────────────────────────────
# This file is read every time AI activities are generated.
# Edit any bullet point below to refine the output.
# Use plain bullet points (- ) under each section heading (##).
# Lines starting with # are comments and are ignored by the AI.
# ─────────────────────────────────────────────────────────────────────────────

## General Sequencing Rules
- Mobilization and site setup must always be the first activity with no predecessors.
- Substructure activities must fully complete before any superstructure work begins.
- Each floor's superstructure must complete before finishing of that floor starts.
- MEP rough-in for a floor should start after the slab of that floor is cast and before finishing begins.
- External works and landscaping should start only after the building structure is topped out.
- Testing and commissioning is always the last phase; it depends on MEP completion and all finishing.
- Do not overlap structural and finishing activities on the same floor.

## Duration Scaling Rules
- For built-up area ≤ 500 sqm: use minimum crew durations (single gang).
- For 500–1500 sqm: use standard durations with 1–2 gangs per trade.
- For 1500–5000 sqm: scale durations up by 30–50%; allow parallel work on different zones.
- For > 5000 sqm: use significantly longer durations with multiple work fronts running in parallel.
- Curing time for RCC: minimum 3 days before deshuttering; include this in slab/column durations.
- Do not assign a duration of less than 1 day to any activity.

## Concrete (RCC) Structural System Rules
- Each floor superstructure sequence: Shuttering Columns → RCC Columns → Deshutter Columns → Shuttering Beams & Slab → RCC Beams & Slab → Deshutter Slab → Curing.
- Raft foundation or isolated footings must follow PCC (Plain Cement Concrete) layer.
- Staircase and lift shaft RCC should be separate activities per floor.
- Do not use terms like "Steel Beam", "Metal Deck", or "Composite Slab" for RCC projects.

## Steel Structural System Rules
- Each floor superstructure sequence: Steel Column Erection → Steel Beam Erection → Purlins/Secondary Members → Metal Deck Laying → Composite Slab Pour → Curing.
- Foundations (footings, raft) use concrete even for steel structures.
- Include bolted connection inspection and high-strength bolt torque checking as separate QA activities.
- Include steel fireproofing (intumescent coating or spray) as a separate activity after erection.
- Do not use terms like "RCC Columns", "Shuttering", or "Deshuttering" for steel superstructure.

## Residential Project Rules
- Include separate finishing activities per apartment type if multiple types exist.
- Balcony waterproofing and tiling should be a separate activity from internal finishing.
- Include utility connection activities: water, electricity, gas meter installation.
- For buildings > 4 floors, include a dedicated lift installation activity.
- Include handing-over inspection and snagging as the final pre-commissioning activity.

## Commercial Project Rules
- Include façade / curtain wall installation as a separate major activity.
- Include raised access flooring for office areas.
- Include false ceiling and lighting layout as separate activities.
- Include BMS (Building Management System) installation and testing.
- Include fire suppression system (sprinklers) as a separate MEP sub-activity.
- Include tenant fit-out shell & core handover as a milestone activity.

## Hospital Project Rules
- Include medical gas pipeline installation (O2, N2O, vacuum, compressed air) as a separate MEP activity.
- Include lead lining installation for X-ray and imaging rooms before finishing.
- Operating theatre and ICU areas need dedicated finishing and HVAC validation activities.
- Include infection-control commissioning and hospital regulatory inspection activities.
- Include nurse call system and patient monitoring infrastructure installation.
- Include DG (Diesel Generator) set installation and testing for critical power backup.
- Pharmacy and clean-room areas require separate validation/qualification activities.

## Basement Rules
- Each basement level must have its own set of activities (do not merge basement levels).
- Basement sequence: Dewatering Setup → Excavation → PCC → Raft/Footings → Retaining Wall → Basement Slab → Waterproofing → Backfilling.
- Basement waterproofing must complete and be inspected before backfilling starts.
- If basements = 0, do not generate any basement-related activities.

## MEP Rules
- MEP should be broken into sub-trades: Electrical, Plumbing & Drainage, HVAC, Fire Fighting.
- Electrical conduit and plumbing rough-in per floor should precede plastering/drywall.
- HVAC duct installation should precede false ceiling activities.
- Final MEP testing and balancing should precede commissioning.

## Quality and Safety Rules
- Include a site safety induction and hoarding activity at the start of Pre-Construction.
- Include concrete cube testing / quality inspection as part of each major RCC pour.
- Include structural steel inspection and weld/bolt testing for steel projects.
- Include a pre-handover inspection / snagging activity near the end of the schedule.
