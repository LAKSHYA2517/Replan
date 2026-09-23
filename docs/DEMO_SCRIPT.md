# RePlan — 5-Minute Submission Video Script & Production Guide
**Track 5: Interruptible Real-Time Agents · Samsung PRISM GenAI Hackathon 2026**

> **Target Duration:** Exactly 4:45 – 4:55 (Hard cut at 4:55. Never exceed 5:00)  
> **Total Word Count:** 720 words (~150 words per minute speaking pace)  
> **Golden Rule (Beat 5):** When the late result lands at 2:30, **hold the frame for 3 full seconds of absolute silence** while both panes are visible. Let the judges read the counters diverge.

---

## Technical Recording Specifications
* **Screen Resolution:** 1080p minimum (1920×1080) at 60 fps.
* **Browser Zoom:** 125% zoom on the RePlan Web Console for crisp legibility after video compression.
* **Audio Track:** Recorded separately with normalized levels (-14 LUFS / -1 dB peak).
* **Execution Mode:** Run `REPLAN_LLM_MODE=replay` or use Synthetic Fixture for 100% deterministic, zero-jitter takes.

---

## Timestamped Storyboard & Voiceover Script

### Beat 1: The Problem & The Core Invariant (0:00 – 0:45 · 110 words)
**Visual:** Full Cockpit View. Agent starts session.
> *"Real-time AI voice agents face a fundamental architectural flaw. When an agent speculates ahead to keep latency low, user speech can change mid-sentence. Conventional agents either wipe out all partial progress and restart from scratch, or worse—let slow, obsolete background tool calls overwrite the present state.*  
>  
> *This is RePlan: a deterministic execution runtime for interruptible AI agents. RePlan is built on one core invariant: **A tool result may affect the current task only if its dependency fingerprint remains mathematically valid under the current state.** Let’s watch how this works in real-time."*

---

### Beat 2: Speculation & In-Flight Dispatches (0:45 – 1:20 · 95 words)
**Visual:** Click `▶ Run Scenario` (Delhi Hotel). Timeline swimlanes fill with blue `RUNNING` bars.
> *"Our user says: 'Find me a hotel in Delhi this weekend under ₹5,000 with breakfast.'*  
>  
> *Instantly, RePlan dispatches search, availability, loyalty status, and booking policy tools in parallel. Each task is tagged with a cryptographic fingerprint derived from its input arguments and current state version v1. The loyalty discount commits at 0.35 seconds, and a reversible room hold is prepared speculatively."*

---

### Beat 3: The Interruption & Predictive Freeze (1:20 – 1:55 · 100 words)
**Visual:** User speech envelope appears. Vertical purple freeze marker triggers at $t=0.95\text{s}$ with the `900 ms lead time` bracket.
> *"Now, the user interrupts: 'Actually Mumbai, but keep everything else.'*  
>  
> *Notice what happens at 0.95 seconds—long before the user finishes speaking. Our fast-path classifier detects a pivot intent on `slots.locality` with 88% confidence. RePlan immediately executes a **predictive freeze** on the blast radius: Delhi search and availability are frozen in purple hatches. The horizontal bracket shows a 900-millisecond freeze lead time before the sentence even ends."*

---

### Beat 4: Selective Reconcile & Work Adoption (1:55 – 2:30 · 105 words)
**Visual:** Switch to Console View. State increments to $v_2$. Reconcile counters update. Adopted cards slide with emerald glow.
> *"At version 2, the Mumbai goal commits. Rather than cancelling everything, our reconciler compares the new dependency graph with in-flight work.*  
>  
> *Notice the 400ms sliding animation: loyalty status and booking policies did not depend on locality, so they are **preserved and adopted**. Reversible Delhi reservations are automatically released via an idempotent compensator. Only Mumbai-specific searches are added. We achieved a 40% work reuse ratio."*

---

### Beat 5: The Showdown — Injecting the Late Stale Result (2:30 – 3:30 · 110 words)
**Visual:** Switch to **⚔️ Dual-Pane Mode**. Press **⚡ Inject Late Result**.
*Left pane shows Conventional Agent. Right pane shows RePlan.*

> *"Now for the critical test. What happens if a slow Delhi search result finally arrives now, while Mumbai is active?*  
>  
> *I’ll press our big red button: **Inject Late Result**."*

*(Action: Click button at 2:45. Late result lands at 2:50.)*

> **[3 SECONDS OF TOTAL SILENCE — DO NOT SPEAK]**  
> *(Judges read: Left counter turns red `WRONG ACTIONS: 1` with alert banner. Right counter stays green `WRONG ACTIONS: 0` with large red diamond `STALE`.)*

> *"The conventional agent on the left blindly committed the late result—corrupting Mumbai and recommending a hotel in Delhi.  
> But on the right, RePlan’s commit gate checked the dispatch fingerprint against version 2, flagged the result as **STALE**, and discarded it. Invariant I2 held."*

---

### Beat 6: Human Control & Deterministic Replay (3:30 – 4:15 · 110 words)
**Visual:** Use Scrubber slider. Show SHA-256 chain hash. Show policy change and explain feature.
> *"RePlan gives humans complete authority over execution. Users can pause, restore named checkpoints, or ask 'Why did you pick this?' and get an answer generated directly from our causal Flight Recorder event log.*  
>  
> *Because every event carries a cryptographic chain hash, we can drag our Replay Scrubber to any sequence number and reproduce the exact bit-for-bit state history with zero network dependency."*

---

### Beat 7: Summary & Conclusion (4:15 – 4:50 · 90 words)
**Visual:** Slide 1 summary / Console overview.
> *"RePlan proves that real-time AI agents do not need to be fragile black boxes. By pairing speculative LLM proposals with deterministic state versions, content-addressed fingerprints, and a transactional commit gate, we eliminate race conditions and recover instantly from interruptions.*  
>  
> *Speculate early. Trace dependencies. Invalidate selectively. Commit only what is still true.  
> Thank you."*

*(Hard cut to final title screen at 4:50 with GitHub repo link and tag `PRISM_GENAI_HACKATHON_Y2026`.)*
