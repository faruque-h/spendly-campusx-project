// main.js — shared behaviour, no frameworks.

// Any form carrying data-confirm asks before submitting. Without JS the form
// still submits: the prompt is an enhancement, not a gate.
document.addEventListener("submit", (event) => {
    const message = event.target.dataset.confirm;
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});
