## Overview
We follow this workflow when designing PCBs for the car. Sticking to this will help you develop hardware smoothly while learning a lot in the process.
## Timeline
Each step of the PCB design process should take approximately this much time (including reviews). Your timeline may vary based on board complexity and overall deadlines, and you'll get faster at iterating as you learn more, but try not to deviate too much from this.

- Requirements & Setup - 1 day
- Schematic & Part Selection - 1-2 weeks
- Layout & Routing - 2 weeks
- Production Files & Documentation - 1 day

The goal of this timeline is to ensure you have some kind of reviewable progress weekly. If you're blocked by another system/dependency, make sure they're aware so you can continue working. Don't be afraid to ask for reviews/help often to stay on track, that's what we're here for :P
## Project Setup
TODO
### Github Repo Setup
First create repo - follow naming conv
Add our pull request (PR) template to the main directory of your repository. Now, whenever you create a PR, the template checklist will show up for you to fill out.
Then create branch
TODO
### Shared Libraries
Then setup shared libraries by cloning submodule
TODO
### Creating a KiCad Project
Then create a new KiCad project within your repo
TODO
### Documentation

## Schematic
TODO
## Part Selection
Do this before selecting footprints
Select footprints
TODO
## Layout & Routing
Put stuff on board
Edge cuts
Mounting
Planes/Stackup
TODO
## Review Process
PCB reviews are handled through Github pull requests. To create a PR, follow [these steps](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request). The PR template should automatically show up, with a checklist to fill out to make sure your PCB is up to standards. Assign reviewers using the sidebar as shown - make sure to assign at least 2 or 3 reviewers (usually your lead/sublead but can be any experienced member). Also ensure you're listed as the assignee for the PR.

![Assign Github Reviewers](img/GH-Reviewers.png)

Now copy the Github link to your PR and send it in the `#review-request` channel on Slack. Mention the reviewers you requested, and feel free to bug them if they don't respond/review in the next couple of days. To keep the review process quick, you should aim to respond to review comments as fast as possible, but make sure you understand what the reviewers are saying. If you're confused about a concept or technical detail, don't hesitate to ask (as a Github reply). It's always better to ask than to take feedback blindly :)
## Generating Production Files
To generate production files for JLC (Gerbers, BOM, and CPL), use the JLCPCB Tools plugin as described [here](../KiCad-Setup/#kicad-jlcpcb-tools).
## Ordering
Follow the [ordering instructions](../Ordering) to order your PCB prototype using JLCPCB. Usually we order in a couple of batches per revision cycle, so reach out to your lead to confirm your order timeline (you may need to speed up development to hit these dates).
