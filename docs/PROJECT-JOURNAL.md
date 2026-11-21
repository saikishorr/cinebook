# CineBook - project journal

A plain-language history of the project, written on 4 Oct 2026 from the working conversation.
It records how the original build went: the steps, the decisions and the problems met. Start with `START-HERE.md`.

## The idea
Build a movie ticket booking system ("CineBook") on AWS, one step at a time, as a learning and training project.
- It will never go live to the public and must stay as close to free as possible.
- Every step is explained first (why, what happens, purpose, part of the architecture), then built, then reviewed.
- Every stage ends with a detailed Word guide, generalised so that any fresher can follow it.

## Working method that was agreed
- One step at a time: implement, review the output, then the next step.
- Guides: Word, page numbers and the author's name in the footer, nothing account-specific; database guides include the ER diagram and table descriptions.
- Python for the code; React for the website; PostgreSQL for the database; region ap-south-1 (Mumbai).

## Phase 1 - the booking system on AWS (27 to 30 Sep 2026)
| Guide | What was built |
|---|---|
| Part 1 | Workstation and AWS account setup |
| Part 2 | PostgreSQL database: 8 tables, sample data, ER diagram |
| Part 3 | Backend API (FastAPI) |
| Part 4 | DynamoDB seat holds (5-minute holds) |
| Part 5 | React website |
| Part 6 | Bookings through an SQS FIFO queue, a worker, and SES email |
| Part 7 | Docker image in ECR |
| Part 8 | VPC network: public, app and database subnets |
| Part 9 | RDS PostgreSQL (private), settings in Parameter Store |
| Part 10 | EC2 Auto Scaling group running the API container |
| Part 11 | Load balancer (accepts CloudFront only) |
| Part 12 | CloudFront - NOT done: waiting for AWS to verify the account |
| Part 13 | Lambda booking worker, CloudWatch dashboard, alarm |
| Part 14 | Terraform: the whole system adopted into code; pause and resume scripts |

Main decisions:
- API runs as a Docker container on EC2 (not plain EC2, not Fargate).
- A NAT instance instead of a NAT gateway, to save cost.
- One `running` switch in Terraform turns the hourly-billed parts off and on (`pause.ps1`, `resume.ps1`).
- Phase 1 was closed on 30 Sep 2026 with the system paused.
- A Project Software Installation Guide was written for all the tools used.

## Phase 2 - booking SMS with a chat link (1 to 3 Oct 2026)
Request: with the confirmation email, also send an SMS containing a link that brings the customer back to the website, to a chatbot.

Decisions:
- Real SMS in India needs DLT registration (business, sender name, templates). To avoid the regulation and paperwork for a training system, **no real SMS is sent**. The SMS is stored and shown in a "Demo Phone" inbox on the website.
- Only registered demo numbers can receive an SMS; the customer must tick a consent box.
- The chat link never expires (the first design had an expiry; it was removed on request). A single link can be switched off.

Steps:
| Step | What |
|---|---|
| 2.1 | Settings: demo numbers, site address, Demo Phone access code (`setup-demo-sms.ps1`, Terraform variables) |
| 2.2 | Database migration 002: `bookings.sms_phone`, `sms_consent`; tables `chat_links`, `sms_messages` |
| 2.3 | API: phone handling, booking check, `GET /chat-links/{code}`, `POST /demo-phone/inbox`, rate limits |
| 2.4 | Worker: `demo_sms.py` creates the link and writes the SMS in a savepoint |
| 2.5 | Website: consent box, Demo Phone page, chat page |
| 2.6 | Local end-to-end test |
| 2.7 | Cloud deployment started; stopped because the new API server never became healthy (solved in Step 3.7) |

## Phase 3 - the chat assistant (3 to 4 Oct 2026)
Request: a chatbot that answers questions about the customer's booking and the information on the website, and politely refuses everything else.

Decisions:
- Model: Gemini API free tier. Amazon Bedrock was tried first, but the new account had a zero daily token quota and one model family needed a use-case form.
- The model is given only three things: the one booking behind the link, the published movies and showtimes, and the Help text.
- The refusal is one fixed sentence shown by our code, not written by the model.
- The assistant is read-only: it cannot cancel, change or refund.

Steps:
| Step | What |
|---|---|
| 3.1 | Model connection check (`check-bedrock.py`, then `check-gemini.py`); design notes |
| 3.2 | Help and info content in one file, `GET /help`, Help page |
| 3.3 | Database migration 003: table `chat_messages` |
| 3.4 | Chat engine and endpoints (`chat_llm.py`, `chat_engine.py`, `routers/chat.py`) |
| 3.5 | Chat panel on the chat page |
| 3.6 | Evaluation with the real model: 39 questions in 8 groups, 39 of 39 passed; live local booking |
| 3.7 | Deployment to AWS (Phases 2 and 3 together) |
| 3.8 | Cloud test, dashboard panels, pause |
| 3.9 | Guides Part 15 and Part 16; handover file |

## Problems met and how they were solved
| Problem | Cause | Fix |
|---|---|---|
| `terraform` not recognised in some terminals | Terminal opened before the install was on PATH | Permanent PATH entry; the scripts also locate Terraform themselves |
| Plan wanted to replace the NAT while paused | A stopped server has no public address, which looked like a change | Added the setting to `ignore_changes` |
| Evaluation question about another booking failed | The model described the customer's own booking, then quoted its own rule | Clearer rule, worked examples, and a filter that blocks replies repeating the instructions |
| New API server never became healthy (1 Oct and 3 Oct) | Start-up took about 6.5 minutes; the Auto Scaling grace period was 5 minutes, so every server was replaced before it finished | Grace period raised to 15 minutes; start-up script now logs to the console, retries network steps and checks the API; `server-log.py` reads the log |
| Booking stuck on "pending" in a local demo | The local worker was not running | Start `worker\run_local.py` |
| Risk in cloud tests | The local worker reads the same queue as the cloud worker | Stop the local worker before any cloud test |
| Ports 5173 / 8000 already in use | An earlier session still running | Stop the process listening on the port |

## The cloud test that closed the build (4 Oct 2026)
- Temporary firewall rule for one internet address only (`cloud-test.ps1`), removed afterwards.
- A booking made through the cloud API was confirmed by the Lambda worker; the demo SMS and chat link were created.
- The assistant, calling the model from inside AWS, answered questions about the booking and the Help content and refused an off-topic question.
- The system was then paused.

## What is still open
1. CloudFront approval from AWS, then the public address, the Part 12 guide, and pointing the SMS links at the public site.
2. Check that the two chat panels on the CloudWatch dashboard show data.
3. Back up the project folder.
4. A stopped database restarts by itself after 7 days; pause again on long breaks.
