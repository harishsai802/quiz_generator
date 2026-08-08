// Countdown timer for the quiz. Auto-submits the form when time runs out.
(function () {
    let remainingSeconds = QUIZ_DURATION_MINUTES * 60;
    const display = document.getElementById("time-display");
    const bar = document.getElementById("timer-bar");
    const form = document.getElementById("quiz-form");

    function render() {
        const m = Math.floor(remainingSeconds / 60);
        const s = remainingSeconds % 60;
        display.textContent = String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
        if (remainingSeconds <= 60) {
            bar.classList.add("low-time");
        }
    }

    render();
    const interval = setInterval(function () {
        remainingSeconds--;
        if (remainingSeconds <= 0) {
            clearInterval(interval);
            display.textContent = "00:00";
            // auto-submit whatever has been answered
            window.quizLeavingIntentionally = true;
            form.submit();
            return;
        }
        render();
    }, 1000);
})();
