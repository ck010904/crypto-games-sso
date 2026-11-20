"use strict";

// 다운로드, 게임 소개, 공지, 이벤트 안내창
document.querySelectorAll("[data-dialog]").forEach((button) => {
  button.addEventListener("click", () => {
    const dialog = document.getElementById(button.dataset.dialog);
    if (dialog && !dialog.open) {
      dialog.showModal();
    }
  });
});

// 안내창 바깥을 클릭하면 닫기
document.querySelectorAll(".site-dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;

    const rect = dialog.getBoundingClientRect();
    const outside =
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom;

    if (outside) dialog.close();
  });
});

// 공지사항 / 업데이트 탭 전환
const tabs = [...document.querySelectorAll("[data-tab]")];

function selectTab(selectedTab) {
  tabs.forEach((tab) => {
    const selected = tab === selectedTab;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;

    const panel = document.getElementById(tab.dataset.tab);
    if (panel) panel.hidden = !selected;
  });
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectTab(tab));

  tab.addEventListener("keydown", (event) => {
    let nextIndex;

    if (event.key === "ArrowRight") {
      nextIndex = (index + 1) % tabs.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = tabs.length - 1;
    } else {
      return;
    }

    event.preventDefault();
    selectTab(tabs[nextIndex]);
    tabs[nextIndex].focus();
  });
});

// 다른 게임 메뉴 바깥을 클릭하면 접기
document.addEventListener("click", (event) => {
  document.querySelectorAll(".game-switch[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});

// Escape로 다른 게임 메뉴 접기
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;

  document.querySelectorAll(".game-switch[open]").forEach((menu) => {
    menu.open = false;
    menu.querySelector("summary").focus();
  });
});
