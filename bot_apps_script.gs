/**
 * Google Apps Script — сбор данных из бота и с сайта
 * Разворачивается как веб-приложение (Развернуть → Новое развёртывание → Веб-приложение)
 * Доступ: для всех (анонимных тоже)
 */

// Шаги воронки в нужном порядке
var FUNNEL_STEPS = ['start', 'q1_shown', 'q1_done', 'q2_done', 'q3_done', 'q4_done', 'q5_done', 'result'];

var STEP_LABELS = {
  'start':    '1 · Запустил бота',
  'q1_shown': '2 · Начал тест (увидел В1)',
  'q1_done':  '3 · Ответил на В1',
  'q2_done':  '4 · Ответил на В2',
  'q3_done':  '5 · Ответил на В3',
  'q4_done':  '6 · Ответил на В4',
  'q5_done':  '7 · Ответил на В5',
  'result':   '8 · Получил результат ✅',
};

// ── Upsert: обновить строку по Telegram ID или добавить новую ─────────────
function upsertByUserId(sh, headers, userId, rowData) {
  if (sh.getLastRow() === 0) {
    ensureHeader(sh, headers);
  }
  var data = sh.getDataRange().getValues();
  var idCol = headers.indexOf('Telegram ID');
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][idCol]) === String(userId)) {
      sh.getRange(i + 1, 1, 1, rowData.length).setValues([rowData]);
      return;
    }
  }
  sh.appendRow(rowData);
}

// ──────────────────────────────────────────────────────────────
// ЕДИНСТВЕННЫЙ ОБРАБОТЧИК — принимает запросы от бота и с сайта
// ──────────────────────────────────────────────────────────────
function doPost(e) {
  try {
    var contentType = e.postData ? (e.postData.type || '') : '';

    if (contentType.indexOf('application/json') !== -1) {
      // ── Заявка с сайта (JSON) ──────────────────────────────
      var data = JSON.parse(e.postData.contents);
      var sh = getSheet('оставили заявку');
      ensureHeader(sh, ['Дата', 'Имя', 'Фамилия', 'Телефон', 'Telegram']);
      sh.appendRow([
        formatDate(new Date()),
        data.firstName || '',
        data.lastName  || '',
        data.phone     || '',
        data.telegram  || '',
      ]);

    } else {
      // ── Запрос от бота (form-encoded) ─────────────────────
      var p = e.parameter || {};
      var event = p.event || '';

      if (event === 'start') {
        // Таб «Зарегистрировались»
        var sh = getSheet('Зарегистрировались');
        ensureHeader(sh, ['Дата', 'Имя', 'Username', 'Telegram ID']);
        sh.appendRow([formatDate(new Date()), p.name || '', p.username || '', p.user_id || '']);
      }

      // Все события воронки → таб «воронка бота» + обновляем «где остановился»
      if (STEP_LABELS[event]) {
        logFunnelEvent(p, event);
        updateLastStep(p, event);
      }

      // Свободный текст → отдельный таб
      if (event === 'free_text') {
        logFreeText(p);
        updateLastStep(p, 'free_text');
      }
    }

    return ContentService.createTextOutput('ok');

  } catch (err) {
    Logger.log('doPost error: ' + err.message);
    return ContentService.createTextOutput('error: ' + err.message);
  }
}

// ── Воронка ────────────────────────────────────────────────────
function logFunnelEvent(p, event) {
  var sh = getSheet('воронка бота');

  // Создаём заголовки если пусто
  if (sh.getLastRow() === 0) {
    var headers = ['Дата', 'Telegram ID', 'Username', 'Имя', 'Шаг', 'Метка шага', 'Результат'];
    sh.appendRow(headers);
    var headerRange = sh.getRange(1, 1, 1, headers.length);
    headerRange.setFontWeight('bold').setBackground('#1F2A46').setFontColor('#FFFFFF');
    sh.setFrozenRows(1);
    // Ширина колонок
    sh.setColumnWidth(1, 140);
    sh.setColumnWidth(2, 110);
    sh.setColumnWidth(3, 130);
    sh.setColumnWidth(4, 160);
    sh.setColumnWidth(5, 80);
    sh.setColumnWidth(6, 210);
    sh.setColumnWidth(7, 220);
  }

  var stepNum = FUNNEL_STEPS.indexOf(event) + 1;

  sh.appendRow([
    formatDate(new Date()),
    p.user_id  || '',
    p.username || '',
    p.name     || '',
    stepNum,
    STEP_LABELS[event] || event,
    p.result   || '',
  ]);

  // Подсвечиваем финальный шаг зелёным
  if (event === 'result') {
    var lastRow = sh.getLastRow();
    sh.getRange(lastRow, 1, 1, 7).setBackground('#D9EAD3');
  }
}

// ── Где остановился (один ряд на пользователя) ────────────────
function updateLastStep(p, event) {
  var sh = getSheet('где остановился');
  var headers = ['Telegram ID', 'Username', 'Имя', 'Последний шаг', 'Метка шага', 'Дата обновления'];

  var stepNum  = FUNNEL_STEPS.indexOf(event) + 1;
  var stepLabel = event === 'free_text'
    ? 'написал сообщение вручную'
    : (STEP_LABELS[event] || event);

  var rowData = [
    p.user_id  || '',
    p.username || '',
    p.name     || '',
    stepNum || '',
    stepLabel,
    formatDate(new Date()),
  ];

  upsertByUserId(sh, headers, p.user_id, rowData);

  // Шапка и форматирование при первом создании
  if (sh.getLastRow() === 1 && sh.getRange(1,1).getValue() !== 'Telegram ID') {
    var headerRange = sh.getRange(1, 1, 1, headers.length);
    headerRange.setFontWeight('bold').setBackground('#1F2A46').setFontColor('#FFFFFF');
    sh.setFrozenRows(1);
    sh.setColumnWidths(1, headers.length, [110, 130, 160, 80, 220, 140]);
  }

  // Зелёный если дошёл до результата
  var rows = sh.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]) === String(p.user_id)) {
      var bg = event === 'result' ? '#D9EAD3' : '#FFFFFF';
      sh.getRange(i + 1, 1, 1, headers.length).setBackground(bg);
      break;
    }
  }
}

// ── Свободные сообщения ────────────────────────────────────────
function logFreeText(p) {
  var sh = getSheet('свободные сообщения');
  var headers = ['Дата', 'Telegram ID', 'Username', 'Имя', 'Шаг воронки', 'Сообщение'];
  ensureHeader(sh, headers);
  sh.appendRow([
    formatDate(new Date()),
    p.user_id  || '',
    p.username || '',
    p.name     || '',
    p.step     || '',
    p.message  || '',
  ]);
}

// ── Вспомогательные ────────────────────────────────────────────
function getSheet(name) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function ensureHeader(sh, headers) {
  if (sh.getLastRow() === 0) {
    sh.appendRow(headers);
    sh.getRange(1, 1, 1, headers.length).setFontWeight('bold').setBackground('#1F2A46').setFontColor('#FFFFFF');
    sh.setFrozenRows(1);
  }
}

function formatDate(d) {
  var pad = function(n){ return n < 10 ? '0' + n : '' + n; };
  return pad(d.getDate()) + '.' + pad(d.getMonth()+1) + '.' + d.getFullYear()
       + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}
