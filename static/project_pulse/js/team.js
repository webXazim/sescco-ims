/* Project Pulse U02: explicit confirmation for team removal. */
document.querySelectorAll('form[data-pulse-confirm-remove]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (!window.confirm('Remove this user from the Project Pulse team?')) {
      event.preventDefault();
    }
  });
});
