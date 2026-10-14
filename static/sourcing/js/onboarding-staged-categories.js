/* Share unsaved company category vocabulary across all capability drafts.
 * Values are suggestions only. Django validates and persists them atomically
 * when the provider is saved. Never create a master on suggestion selection.
 */
(() => {
  'use strict';
  window.SourcingStagedCategories = {
    create(root, options) {
      const rows = root.querySelector('[data-onboarding-rows]');
      const categorySuffix = options.categoryField;
      const newCategorySuffix = options.newCategoryField;
      const nameSuffix = options.nameField;
      const stagedKey = options.stagedKey;
      const freeText = !!options.freeText;
      function field(row, suffix) {
        return [...row.querySelectorAll('input,select,textarea')]
          .find(input => input.name.endsWith(`-${suffix}`));
      }
      function eligible(row) {
        return !field(row, 'DELETE')?.checked &&
          row.dataset[stagedKey] === '1' &&
          field(row, nameSuffix)?.value.trim();
      }
      function refresh() {
        const list = new Map();
        const all = [...rows.querySelectorAll('[data-onboarding-row]')];
        for (const row of all) {
          if (!eligible(row)) continue;
          const category = field(row, categorySuffix);
          if (!category) continue;
          const name = (freeText ? category.value :
            category.value === '__new__' ? field(row, newCategorySuffix)?.value : '') || '';
          const label = name.trim().replace(/\s+/g, ' ');
          if (label && label.length <= 120 && !list.has(label.toLocaleLowerCase())) {
            list.set(label.toLocaleLowerCase(), label);
          }
        }
        for (const row of all) {
          const category = field(row, categorySuffix);
          if (!category) continue;
          if (freeText) {
            let datalist = row.querySelector('[data-draft-category-datalist]');
            if (!datalist) {
              datalist = document.createElement('datalist');
              datalist.id = `sourcing-draft-category-${category.name.replace(/[^a-z0-9]+/gi, '-')}`;
              datalist.dataset.draftCategoryDatalist = '';
              category.insertAdjacentElement('afterend', datalist);
              category.setAttribute('list', datalist.id);
            }
            datalist.replaceChildren();
            for (const label of list.values()) {
              const suggestion = document.createElement('option');
              suggestion.value = label;
              datalist.append(suggestion);
            }
            continue;
          }
          // Only inject dynamic values; keep Django-provided saved categories.
          for (const option of [...category.querySelectorAll('option[data-staged-category]')]) {
            option.remove();
          }
          const existing = new Set([...category.options].map(o => o.value.toLocaleLowerCase()));
          const createOption = [...category.options].find(o => o.value === '__new__');
          for (const label of list.values()) {
            if (existing.has(label.toLocaleLowerCase())) continue;
            const option = document.createElement('option');
            option.value = label;
            option.textContent = `${label} (this form)`;
            option.dataset.stagedCategory = '';
            category.insertBefore(option, createOption || null);
            existing.add(label.toLocaleLowerCase());
          }
          // If an upstream draft was removed, do not silently submit an
          // orphaned category. The user must reselect or create a new one.
          if (category.value === '' && category.dataset.stagedSelected) {
            const current = category.dataset.stagedSelected;
            if ([...category.options].some(o => o.value === current)) category.value = current;
            else {
              category.value = '';
              category.dispatchEvent(new Event('change', { bubbles: true }));
            }
          }
          category.dataset.stagedSelected = category.value;
        }
      }
      function mount(row) {
        const category = field(row, categorySuffix);
        if (category && !category.dataset.stagedCategoryBound) {
          category.dataset.stagedCategoryBound = '1';
          category.addEventListener('change', () => {
            category.dataset.stagedSelected = category.value;
          });
        }
        refresh();
      }
      return { refresh, mount };
    },
  };
})();
