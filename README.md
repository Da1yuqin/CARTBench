# <img src="assets/cartbench-logo.png" alt="CARTBench logo" width="64"> CARTBench

**Explore:** [Review the data](review/check.html) · [Run an evaluation](runner/run.html) · [Output examples](examples/index.html)

**Resources:** [Paper](https://arxiv.org/abs/2611.05862) · [HF Papers](https://huggingface.co/papers/2611.05862) · [Hugging Face Dataset](https://huggingface.co/datasets/dayll/CARTBench)

Open Review directly and select `data/data.json`, or start both interactive pages with `python3 run.py --serve`. The Run page links to the local evaluation interface; saved examples can be opened directly.

CARTBench evaluates shopping advice for **Complex and Ambiguous Requests with Timelines**. It connects timestamped shopping dialogue and supplied product evidence to case-specific checks of required behavior, additional decision help, and safety.

<p align="center"><img src="assets/case.png" alt="A CART case: gloves for stationary photography at minus 30 degrees Celsius, with camera controls and non-electric insulation" width="920"></p>

*Two assessed replies to a glove-selection request differ in evidence support, camera-control trade-offs, and safety. The user already has a thin fleece liner and needs an outer layer that does not rely only on electricity for two-hour stationary photography at minus 30 degrees Celsius. Colors connect reply excerpts to the selected checks; the figure also reports full-reply pass counts.*

A recommendation model receives the dialogue and product information. A judge then evaluates its newly generated reply against the case-specific rubric. Core, Excellence, and Safety are scored separately; earning Excellence never compensates for a Core error.

## Explore the Benchmark

- **Expert Review:** search all cases, follow the dialogue timeline, inspect product evidence and tier-specific criteria, and validate source quotations and input bindings.
- **Evaluation runner:** configure Agent and Judge endpoints, select one case or the full benchmark, and follow progress in the web interface.
- **Shopping-guide examples:** browse six recorded evaluations, including GPT-6.1-Sol, with dialogue history, formatted recommendations, product cards, and detailed evaluation evidence.
- **Saved result pages:** each evaluation generates JSON, an individual HTML page, and an index of completed results.

## Main Results

The paper evaluates **10 model configurations three times on all 169 cases**, using 1,328 criteria: 760 Core, 553 Excellence, and 15 Safety. The tables report expert-confirmed resolved-check pass rates (%) as **mean ± sample standard deviation** across the three evaluations. Higher rates are better. Each rate uses `pass / (pass + fail)`; not-applicable and unresolved outcomes are tracked separately.

Core checks required behavior, factual support, and feasibility. Excellence rewards concrete comparisons, priorities, and conditional guidance that improve a purchase decision. Safety checks case-specific recommendation risks.

### Commercial API models

| Model | Core ↑ | Excellence ↑ | Safety ↑ |
| --- | ---: | ---: | ---: |
| MiMo-V2.6-Pro | 87.0 ± 1.3 | 32.9 ± 1.4 | 95.6 ± 3.8 |
| DeepSeek-V4-Pro | 91.0 ± 0.4 | 36.3 ± 7.8 | 95.6 ± 3.8 |
| MiniMax-M3 | 88.8 ± 0.5 | 26.4 ± 0.5 | 82.2 ± 13.9 |
| Kimi-K3 | 89.3 ± 0.6 | 37.2 ± 4.1 | 91.1 ± 3.8 |
| Claude-Opus-5 | 89.0 ± 1.0 | 39.8 ± 1.2 | 91.1 ± 10.2 |
| Qwen3.8-Max | 95.4 ± 0.6 | 37.2 ± 3.3 | 93.3 ± 6.7 |
| GPT-6.1-Sol | 95.9 ± 0.6 | 29.6 ± 1.1 | 100.0 ± 0.0 |

### Local open-weight models

| Model | Core ↑ | Excellence ↑ | Safety ↑ |
| --- | ---: | ---: | ---: |
| Qwen3.5-35B-A3B | 68.9 ± 0.6 | 21.1 ± 1.4 | 60.0 ± 11.5 |
| Qwen3.5-122B-A10B | 71.3 ± 1.0 | 25.4 ± 1.9 | 71.1 ± 21.4 |
| Qwen3.5-397B-A17B | 80.3 ± 0.6 | 18.9 ± 1.1 | 84.4 ± 7.7 |

## Understanding-to-Execution Gap

**Meeting required behavior does not ensure high-quality purchase advice.** Three of ten configurations exceed 90% mean Core, while none reaches 40% mean Excellence. GPT-6.1-Sol scores 95.9 ± 0.6% on Core but 29.6 ± 1.1% on Excellence; Claude-Opus-5 has the highest mean Excellence at 39.8 ± 1.2%. This **understanding-to-execution gap** persists under Principle-Guided CART Prompting: a reply can satisfy basic obligations while omitting useful comparisons, purchase priorities, or conditional decision guidance.

Diagnosis of the first evaluation identifies three recurring Core failure modes in every model: **Product Evidence Overreach** (unsupported product claims), **Product Fit Leap** (unjustified suitability for the current user), and **Shopping Uncertainty Collapse** (treating unknown needs or conditions as settled). Among replies passing all resolved goal, requirement, uncertainty, and evidence checks and eligible for the plan analysis, 13.0% still fail a plan check (equal model weights; 95% interval: 8.1–18.4%).

<details>
<summary>Capability, scenario, and cost results</summary>

GA = goal alignment, RA = requirement adherence, and UP = uncertainty preservation. The scenario columns report Excellence within overlapping Constraints, Ambiguity, and Context groups; they cannot be averaged to recover overall Excellence. Overall Core pools all six Core capabilities.

| Model | Exc. Constraints ↑ | Exc. Ambiguity ↑ | Exc. Context ↑ | GA ↑ | RA ↑ | UP ↑ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MiMo-V2.6-Pro | 30.1 ± 1.4 | 31.9 ± 1.1 | 34.1 ± 2.2 | 98.7 ± 0.9 | 92.4 ± 2.8 | 88.4 ± 4.2 |
| DeepSeek-V4-Pro | 34.8 ± 8.2 | 36.9 ± 9.0 | 37.0 ± 6.9 | 98.2 ± 1.2 | 95.6 ± 0.3 | 93.1 ± 6.1 |
| MiniMax-M3 | 23.5 ± 1.0 | 24.1 ± 0.7 | 27.8 ± 1.9 | 97.6 ± 1.4 | 93.4 ± 1.6 | 91.7 ± 3.7 |
| Kimi-K3 | 35.3 ± 3.5 | 38.4 ± 4.9 | 37.3 ± 5.6 | 98.4 ± 0.8 | 93.6 ± 0.7 | 87.5 ± 2.8 |
| Claude-Opus-5 | 37.1 ± 1.1 | 38.8 ± 1.8 | 40.9 ± 2.2 | 99.0 ± 0.5 | 93.8 ± 0.9 | 91.2 ± 0.9 |
| Qwen3.8-Max | 35.1 ± 2.8 | 37.6 ± 2.4 | 37.9 ± 3.3 | 99.2 ± 0.0 | 97.6 ± 0.6 | 93.5 ± 3.2 |
| GPT-6.1-Sol | 26.8 ± 1.5 | 30.8 ± 1.1 | 32.0 ± 1.8 | 98.4 ± 0.8 | 97.0 ± 0.6 | 96.2 ± 0.8 |
| Qwen3.5-35B-A3B | 19.9 ± 0.9 | 19.8 ± 2.3 | 22.4 ± 1.8 | 90.8 ± 1.8 | 81.7 ± 1.3 | 67.1 ± 4.1 |
| Qwen3.5-122B-A10B | 22.7 ± 2.3 | 24.8 ± 2.3 | 27.7 ± 1.4 | 91.3 ± 0.8 | 85.3 ± 2.1 | 65.7 ± 3.3 |
| Qwen3.5-397B-A17B | 17.6 ± 1.6 | 16.7 ± 0.8 | 19.9 ± 0.5 | 95.8 ± 2.0 | 87.6 ± 0.3 | 78.6 ± 0.7 |

Costs are the estimated totals for 169 recommendation requests and 169 judging requests in the first evaluation, using official vendor reference prices. Both columns use USD; CNY prices are converted at 6.7313 CNY per USD. A dash denotes unmeasured local inference cost.

| Model | Inference (USD) ↓ | Judge (USD) ↓ |
| --- | ---: | ---: |
| MiMo-V2.6-Pro | 0.79 | 8.26 |
| DeepSeek-V4-Pro | 3.06 | 8.50 |
| MiniMax-M3 | 1.96 | 7.99 |
| Kimi-K3 | 10.17 | 8.39 |
| Claude-Opus-5 | 15.19 | 8.44 |
| Qwen3.8-Max | 5.28 | 9.26 |
| GPT-6.1-Sol | 6.67 | 7.76 |
| Qwen3.5-35B-A3B | — | 8.71 |
| Qwen3.5-122B-A10B | — | 8.98 |
| Qwen3.5-397B-A17B | — | 8.22 |

</details>

The tables report the paper's recorded evaluations.

## Output Examples

Open six recorded evaluations covering contrasting shopping tasks and model configurations:

| Case | Model | Shopping task |
| --- | --- | --- |
| [S002](examples/S002.html) | GPT-6.1-Sol | Cold-weather gloves for stationary photography |
| [H06](examples/H06.html) | Qwen3.8-Max | Hospital-bag preparation with existing supplies |
| [H02](examples/H02.html) | Claude-Opus-5 | A camera backpack with carrying and lens constraints |
| [H04](examples/H04.html) | DeepSeek-V4-Pro | Aquarium purchases, existing equipment, and unknown conditions |
| [N029](examples/N029.html) | GPT-6.1-Sol | Dorm-room priorities after a change of context |
| [N130](examples/N130.html) | Kimi-K3 | Weekend outfit choice after a changed occasion |

Each page presents the timestamped dialogue as conversation bubbles, followed by the recommendation and its criterion judgments. Product names replace webpage references in the display. Product cards appear beside the relevant advice with local style previews and an inactive **Add to bag** button. The gallery and new result pages use the same interface.

Each new evaluation saves `outputs/<query_id>.json` and a standalone `outputs/<query_id>.html`. Open `outputs/index.html` to browse saved results, or follow **Open full result page** in the Run interface. Result pages show the reply, tier pass rates, each criterion's verdict and reason, and quoted evidence.

## Data and Evaluation

[`data/data.json`](data/data.json) contains 169 cases across 17 retail domains, 1,603 product records, and all 1,328 criteria. Each case includes `query_id`, `messages`, `input_sha256`, and `rubrics`. Case identifiers, timestamps, numeric values, and null profiles are preserved. Evidence quotations refer to the supplied source text, and input hashes bind each rubric to the messages actually supplied to the model.

The same public data is available on [Hugging Face](https://huggingface.co/datasets/dayll/CARTBench). Load all 169 evaluation cases with the optional `datasets` library:

```python
from datasets import load_dataset

dataset = load_dataset("dayll/CARTBench")
case = dataset["test"][0]
```

[`prompt/agent.md`](prompt/agent.md) implements Principle-Guided CART Prompting. [`prompt/judge.md`](prompt/judge.md) contains the judging instruction and complete runtime contract. Product information comes from an internal product search platform and is supplied with each case.

The judge scores only the newly generated `target_response`. The runner checks every rubric identifier, input binding, response quotation, and source quotation before saving results. It reports the six Core capabilities separately: GA (goal alignment), RA (requirement adherence), UP (uncertainty preservation), EF (evidence fidelity), PV (plan validity), and DS (decision support). The executable field value `enhancement` denotes Excellence.

## Quick Start

Requires Python 3.9+ and its standard library.

Validate the complete data:

```sh
python3 run.py --all --dry-run
```

Start the local web interface:

```sh
python3 run.py --serve
```

Open **[Expert Review](http://127.0.0.1:8765/review)** to search the data, inspect dialogue, product evidence and criteria, and run automatic validation. Open **[Run Evaluation](http://127.0.0.1:8765/run)** to select a case or the full data, launch an API evaluation, and follow its progress and results.

To configure an API evaluation, copy the example configuration and set the endpoint and model for both roles:

```sh
cp config.example.json config.json
export CARTBENCH_AGENT_KEY='YOUR_AGENT_KEY'
export CARTBENCH_JUDGE_KEY='YOUR_JUDGE_KEY'
```

The runner uses OpenAI-compatible Chat Completions APIs. API runs may incur provider charges. Start the web server from a terminal with these environment variables set, or run from the command line:

```sh
python3 run.py --case H08 --run
python3 run.py --all --run
python3 run.py --help
```

Results are written to `outputs/` beside the configuration file. Existing results are preserved; use a separate `output_dir` for another evaluation. A complete run prints pooled rates across cases. Resource and output paths are resolved from the runner or configuration file, so the package can be moved and launched from another directory.

## Repository Layout

```text
run.py              Command-line entry point
tool/              Dataset validation, API evaluation, reports and local server
review/            Expert review and automatic data checks
runner/            Web evaluation interface
examples/          Representative saved evaluation pages
data/              Benchmark data
prompt/            Agent and Judge instructions
assets/            Logo, case figure and shared display styles
assets/example/    Example and product illustrations
```

## License

Original code, prompts, and documentation use the [MIT license](LICENSE). The benchmark is provided for academic research and evaluation; third-party product text and trademarks retain their original rights.
