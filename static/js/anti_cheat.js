// ==========================================================
// Anti-cheating protections for the quiz page
// ==========================================================
(function () {
    let violationHandled = false; // avoid firing multiple times for one regenerate

    // Tracks whether the page is unloading because of a legitimate,
    // intentional quiz action (clicking "Submit Quiz", the timer running
    // out and auto-submitting, or being redirected after a regenerate).
    // Without this flag, the `beforeunload` handler below fired on EVERY
    // navigation -- including a normal Submit click -- popping up a
    // "leaving will be recorded as a violation" confirmation dialog that
    // made Submit look broken.
    window.quizLeavingIntentionally = false;

    function showWarning(msg) {
        const el = document.getElementById("quiz-warning");
        if (el) {
            el.style.display = "block";
            el.textContent = msg;
        }
    }

    function reportViolation(type) {
        if (violationHandled) return;

        fetch(LOG_VIOLATION_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ attempt_id: ATTEMPT_ID, violation_type: type })
        })
        .then(res => res.json())
        .then(data => {
            if (data.regenerate && data.new_attempt_url) {
                violationHandled = true;
                showWarning(
                    "Violation detected (" + type + "). Your quiz has been regenerated with new questions."
                );
                setTimeout(() => {
                    window.quizLeavingIntentionally = true;
                    window.location.href = data.new_attempt_url;
                }, 1500);
            } else {
                showWarning("Warning: " + type + " detected. Stay on this tab, further violations will regenerate your quiz.");
            }
        })
        .catch(err => console.error("Violation log failed", err));
    }

    // ---- 1. Detect tab switch / minimizing ----
    document.addEventListener("visibilitychange", function () {
        if (document.hidden) {
            reportViolation("tab_switch");
        }
    });

    // ---- 2. Detect window losing focus (alt-tab, other app) ----
    window.addEventListener("blur", function () {
        reportViolation("window_blur");
    });

    // ---- 3. Detect attempt to close / navigate away ----
    window.addEventListener("beforeunload", function (e) {
        // Don't treat submitting the quiz (or an automatic redirect after
        // a violation regenerate) as a "closing the tab" violation.
        if (window.quizLeavingIntentionally) return;

        // Best-effort synchronous beacon; browsers limit what can run here
        navigator.sendBeacon(
            LOG_VIOLATION_URL,
            new Blob([JSON.stringify({ attempt_id: ATTEMPT_ID, violation_type: "close_attempt" })],
                      { type: "application/json" })
        );
        e.preventDefault();
        e.returnValue = "Leaving this page will be recorded as a quiz violation. Are you sure?";
        return e.returnValue;
    });

    // ---- 3b. Mark intentional submission of the quiz form ----
    document.addEventListener("DOMContentLoaded", function () {
        const quizForm = document.getElementById("quiz-form");
        if (quizForm) {
            quizForm.addEventListener("submit", function () {
                window.quizLeavingIntentionally = true;
            });
        }
    });

    // ---- 4. Disable text copy ----
    document.addEventListener("copy", function (e) {
        e.preventDefault();
        reportViolation("copy_attempt");
    });
    document.addEventListener("cut", function (e) { e.preventDefault(); });

    // ---- 5. Disable right-click context menu ----
    document.addEventListener("contextmenu", function (e) {
        e.preventDefault();
        reportViolation("right_click");
    });

    // ---- 6. Disable common devtools / copy shortcuts ----
    document.addEventListener("keydown", function (e) {
        const key = e.key.toLowerCase();
        const blockedCombo = (e.ctrlKey || e.metaKey) && ["c", "u", "s", "p"].includes(key);
        const devtoolsKey = key === "f12" || ((e.ctrlKey || e.metaKey) && e.shiftKey && ["i", "j", "c"].includes(key));
        if (blockedCombo || devtoolsKey) {
            e.preventDefault();
        }
    });

    // ---- 7. Disable text selection everywhere on quiz page ----
    document.body.style.userSelect = "none";
})();
