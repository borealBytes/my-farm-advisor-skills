# AI Usage Documentation

AI tools (an agentic coding assistant running in-terminal, model backed
by OpenRouter/LiteLLM) were used as an implementation and debugging tool
throughout this project, directed and reviewed at every step. This
section documents where judgment and decision-making were mine, and
where the AI's role was execution.

## My Role: Direction, Review, and Decisions

Every meaningful decision in this project was mine, made after reviewing
what the AI produced — not accepted on trust:

- **Planning:** I had the AI propose a dashboard narrative and structure
  based on my existing Assignment #01–#03 datasets, then made the actual
  calls myself: output format (interactive HTML), which grower to use,
  where the new skill should live in the repo, whether NDVI results
  should be cached, and how the Soil Health Index should be weighted.

- **Catching broken output:** After the first dashboard build, I
  personally opened the rendered HTML, went through all 5 charts, and
  compared them against the underlying data table. I found the
  geospatial map was completely blank, the NDVI and Soil Health charts
  had misleading unlabeled axis scales, and the rotation matrix had no
  legend — none of this was surfaced by the AI on its own; I found it by
  inspecting the actual output.

- **Not trusting claimed fixes:** When the AI reported the map bug fixed,
  I re-checked the rendered output myself and found it was still broken
  (visible legend and basemap, but no field polygons). I sent it back for
  a second, deeper diagnosis rather than accepting the first explanation.

- **The core analytical catch of the project:** Once the map finally
  rendered field shapes, I noticed the fields were implausibly spread
  across ~140 miles for what was supposed to be a single small farm
  operation. I flagged this myself as not making physical sense and
  directed the investigation into why, rather than treating the chart as
  ground truth.

- **The scoping decision:** Once the AI traced the issue to an upstream
  demo-data generation script pulling fields from across an entire
  region, I made the call on how to handle it — filtering the dashboard
  to the realistic field subset within the new skill, rather than
  editing shared upstream pipeline files that other parts of the
  coursework depend on. I then verified the regenerated dashboard's
  acreage and field count against the grower's independently-existing
  farm report before accepting it as correct.

- **Interpretation:** The written analysis of the findings (rotation
  patterns, soil health, NDVI) reflects my own reading of the confirmed,
  verified data values — I reviewed it against the dashboard myself
  before finalizing.

## Where AI Did the Implementation

The AI wrote the dashboard skill's code (the Plotly chart generation, the
data-loading/joining logic, the skill's file scaffolding) and diagnosed
the technical root causes of the bugs above (a frozen Plotly CDN version,
missing axis-range constraints, missing legend logic) once I had
identified that something was wrong and described what I was seeing.

## Summary

The technical implementation was AI-assisted; the direction, quality
control, and the project's most important finding — catching a
data-integrity issue that would have made the final dashboard
misleading — came from reviewing the AI's output critically rather than
accepting it at face value.
