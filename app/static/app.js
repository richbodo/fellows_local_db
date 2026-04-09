// EHF Fellows directory – two-phase load: list first, then full data in background.
// Detail layout matches reference: table-like rows, purple/grey section headers, two columns.

(function () {
  var DETAIL_PAGE_TITLE = 'Confidential - Fellows Local-Only Directory Development Project';
  var fellowsBySlug = new Map();
  var list = [];
  var displayedList = [];
  var loadingEl = document.getElementById('loading');
  var appWrapEl = document.getElementById('app-wrap');
  var connectionBannerEl = document.getElementById('connection-banner');
  var directoryEl = document.getElementById('directory');
  var directoryListEl = document.getElementById('directory-list') || directoryEl;
  var searchInputEl = document.getElementById('search-input');
  var searchStatusEl = document.getElementById('search-status');
  var searchDebounceId = null;
  var nlSearchContainerEl = document.getElementById('nl-search-container');
  var nlSearchInputEl = document.getElementById('nl-search-input');
  var nlSearchButtonEl = document.getElementById('nl-search-button');
  var nlSearchStatusEl = document.getElementById('nl-search-status');
  var detailEl = document.getElementById('detail');
  var fullFellowsCache = null;

  function showLoading(show) {
    loadingEl.classList.toggle('hidden', !show);
  }

  function showApp(show) {
    if (appWrapEl) appWrapEl.classList.toggle('hidden', !show);
  }

  function renderDirectoryList(items) {
    var ul = document.createElement('ul');
    items.forEach(function (f) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#/fellow/' + encodeURIComponent(f.slug || '');
      var displayName = (f.name && String(f.name).trim()) ? f.name : 'Unknown';
      a.textContent = displayName;
      li.appendChild(a);
      ul.appendChild(li);
    });
    directoryListEl.innerHTML = '';
    directoryListEl.appendChild(ul);
  }

  function renderDirectory() {
    if (!list.length) {
      directoryListEl.innerHTML = '<p class="placeholder">No fellows loaded.</p>';
      return;
    }
    renderDirectoryList(list);
    displayedList = list;
    showLoading(false);
    showApp(true);
  }

  function setSearchStatus(msg) {
    if (!searchStatusEl) return;
    searchStatusEl.textContent = msg || '';
  }

  function setNlSearchStatus(msg) {
    if (!nlSearchStatusEl) return;
    nlSearchStatusEl.textContent = msg || '';
  }

  function section(title, body, secondary) {
    if (!body || !body.trim()) return '';
    var titleClass = 'detail-section-title' + (secondary ? ' detail-section-title--secondary' : '');
    return '<div class="detail-section"><h3 class="' + titleClass + '">' + escapeHtml(title) + '</h3><div class="detail-section-body">' + body + '</div></div>';
  }

  /** Section that always renders; when body is empty, no text (no "—"), just header and blank line. */
  function sectionAlways(title, body, secondary) {
    var hasBody = body && String(body).trim();
    var content = hasBody ? body : '';
    var bodyClass = 'detail-section-body' + (!hasBody ? ' detail-section-body--empty' : '');
    var titleClass = 'detail-section-title' + (secondary ? ' detail-section-title--secondary' : '');
    return '<div class="detail-section"><h3 class="' + titleClass + '">' + escapeHtml(title) + '</h3><div class="' + bodyClass + '">' + content + '</div></div>';
  }

  function fieldRow(label, value) {
    if (value == null || String(value).trim() === '') return '';
    return '<tr><td class="field-label">' + escapeHtml(label) + '</td><td class="field-value">' + value + '</td></tr>';
  }

  /** Work subheader block: label only, optional value below (no text/dash when empty). Single blank line between blocks. */
  function workBlock(label, value) {
    var hasVal = value != null && String(value).trim() !== '';
    var valueHtml = hasVal ? '<div class="work-value">' + escapeHtml(value) + '</div>' : '';
    return '<div class="work-block"><div class="work-subheader">' + escapeHtml(label) + '</div>' + valueHtml + '</div>';
  }

  function tableFromRows(rows) {
    var joined = rows.join('');
    if (!joined) return '';
    return '<table><tbody>' + joined + '</tbody></table>';
  }

  function renderDetail(fellow) {
    if (!fellow) {
      detailEl.innerHTML = '<p class="placeholder">Select a fellow from the list.</p>';
      detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      return;
    }
    var name = fellow.name || fellow.slug || 'Unknown';
    var slug = fellow.slug || '';
    var leftTop = '';
    var leftRest = '';

    var demo = [fellow.gender_pronouns, fellow.ethnicity].filter(Boolean).join(' | ');
    leftTop += '<h2 class="detail-name">' + escapeHtml(name) + '</h2>';
    if (demo) leftTop += '<p class="detail-demographics">' + escapeHtml(demo) + '</p>';
    leftTop += '<div class="profile-image-wrap"><img class="profile-image" data-slug="' + escapeHtml(slug) + '" src="/images/' + escapeHtml(slug) + '.jpg" alt="' + escapeHtml(name) + '"></div>';
    if (fellow.bio_tagline) leftTop += '<p class="detail-tagline">' + escapeHtml(fellow.bio_tagline) + '</p>';

    var howRows = [];
    if (fellow.fellow_status) howRows.push(fieldRow('Fellow Status', escapeHtml(fellow.fellow_status)));
    if (fellow.fellow_type) howRows.push(fieldRow('Fellow Type', escapeHtml(fellow.fellow_type)));
    if (fellow.key_links_urls && fellow.key_links_urls.length) {
      var linkLabels = (fellow.key_links || '').split(',');
      var linkHtml = fellow.key_links_urls.map(function (url, i) {
        var label = (linkLabels[i] || url).trim();
        return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' + escapeHtml(label) + '</a>';
      }).join(', ');
      howRows.push(fieldRow('Key Links', linkHtml));
    }
    if (fellow.contact_email) howRows.push(fieldRow('Contact Email', '<a href="mailto:' + escapeHtml(fellow.contact_email) + '">' + escapeHtml(fellow.contact_email) + '</a>'));
    if (fellow.mobile_number) howRows.push(fieldRow('Mobile Number', escapeHtml(String(fellow.mobile_number))));
    if (fellow.cohort) howRows.push(fieldRow('Cohort', escapeHtml(fellow.cohort)));
    leftRest += section('How to Connect', tableFromRows(howRows));

    var geoRows = [];
    if (fellow.primary_citizenship) geoRows.push(fieldRow('Primary Citizenship', escapeHtml(fellow.primary_citizenship)));
    if (fellow.all_citizenships) geoRows.push(fieldRow('All Citizenships', escapeHtml(fellow.all_citizenships)));
    if (fellow.primary_global_region_of_citizenship) geoRows.push(fieldRow('Primary Global Region of Citizenship', escapeHtml(fellow.primary_global_region_of_citizenship)));
    if (fellow.global_networks) geoRows.push(fieldRow('Global Networks', escapeHtml(fellow.global_networks)));
    if (fellow.currently_based_in) geoRows.push(fieldRow('Currently Based In', escapeHtml(fellow.currently_based_in)));
    if (fellow.global_regions_currently_based_in) geoRows.push(fieldRow('Global Regions Currently Based In', escapeHtml(fellow.global_regions_currently_based_in)));
    leftRest += section('Geography', tableFromRows(geoRows));

    leftRest += section('Search Tags', (fellow.search_tags && String(fellow.search_tags).trim()) ? escapeHtml(fellow.search_tags) : '—', true);
    if (fellow.this_profile_last_updated) leftRest += section('This Profile Last Updated', '<span class="profile-updated-date">' + escapeHtml(fellow.this_profile_last_updated) + '</span>', true);

    var workRows = [];
    workRows.push(workBlock('Ventures', fellow.ventures));
    workRows.push(workBlock('Industries', fellow.industries));
    workRows.push(workBlock('Industries - Other', fellow.industries_other));
    workRows.push(workBlock('What is your main mode of working?', fellow.what_is_your_main_mode_of_working));
    workRows.push(workBlock('Do you consider yourself an investor in one or more of these categories?', fellow.do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories));
    workRows.push(workBlock('What are the main types of organisations you serve?', fellow.what_are_the_main_types_of_organisations_you_serve));
    var workBody = workRows.join('');
    var rightTop = section('Work', workBody);

    var rightRest = '';
    rightRest += sectionAlways('Career Highlights', fellow.career_highlights ? escapeHtml(fellow.career_highlights) : '', true);
    rightRest += sectionAlways("How I'm looking to support the NZ ecosystem", fellow.how_im_looking_to_support_the_nz_ecosystem ? escapeHtml(fellow.how_im_looking_to_support_the_nz_ecosystem) : '', true);
    rightRest += sectionAlways('Key Networks', fellow.key_networks ? escapeHtml(fellow.key_networks) : '', true);

    // Build prev/next navigation arrows
    var navHtml = '';
    if (fellow.slug && displayedList.length) {
      var idx = -1;
      for (var i = 0; i < displayedList.length; i++) {
        if (displayedList[i].slug === fellow.slug) { idx = i; break; }
      }
      if (idx !== -1) {
        var prevSlug = idx > 0 ? displayedList[idx - 1].slug : null;
        var nextSlug = idx < displayedList.length - 1 ? displayedList[idx + 1].slug : null;
        var prevClass = 'fellow-nav-arrow fellow-nav-arrow--prev' + (prevSlug ? '' : ' fellow-nav-arrow--hidden');
        var nextClass = 'fellow-nav-arrow fellow-nav-arrow--next' + (nextSlug ? '' : ' fellow-nav-arrow--hidden');
        var prevHref = prevSlug ? '#/fellow/' + encodeURIComponent(prevSlug) : '#';
        var nextHref = nextSlug ? '#/fellow/' + encodeURIComponent(nextSlug) : '#';
        navHtml = '<nav class="fellow-nav">' +
          '<a class="' + prevClass + '" href="' + prevHref + '" aria-label="Previous fellow">&larr;</a>' +
          '<a class="' + nextClass + '" href="' + nextHref + '" aria-label="Next fellow">&rarr;</a>' +
          '<span class="fellow-nav-hint">or use arrow keys</span>' +
          '</nav>';
      }
    }

    var html = '<header class="detail-page-title">' + escapeHtml(DETAIL_PAGE_TITLE) + '</header>' +
      navHtml +
      '<div class="detail-grid">' +
      '<div class="detail-column detail-left-top">' + leftTop + '</div>' +
      '<div class="detail-column detail-right-top">' + rightTop + '</div>' +
      '<div class="detail-column detail-left-rest">' + leftRest + '</div>' +
      '<div class="detail-column detail-right-rest">' + rightRest + '</div>' +
      '</div>';
    detailEl.innerHTML = html;
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    var img = detailEl.querySelector('.profile-image');
    if (img) {
      img.onerror = function () {
        var s = img.getAttribute('data-slug');
        if (img.src.indexOf('.png') === -1 && s) {
          img.src = '/images/' + s + '.png';
          img.onerror = function () { showImagePlaceholder(img); };
        } else {
          showImagePlaceholder(img);
        }
      };
    }
  }

  function showImagePlaceholder(imgEl) {
    imgEl.onerror = null;
    imgEl.style.display = 'none';
    var p = document.createElement('span');
    p.className = 'placeholder';
    p.textContent = 'No image';
    imgEl.parentNode.appendChild(p);
  }

  function escapeHtml(s) {
    if (s == null) return '';
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function statsSection(title, items, color) {
    if (!items || !items.length) return '';
    var maxCount = items[0].count;
    var barHeight = 28;
    var labelWidth = 220;
    var gap = 4;
    var chartWidth = 500;
    var svgHeight = items.length * (barHeight + gap);
    var totalWidth = labelWidth + chartWidth + 60;

    var svg = '<svg class="stats-chart" width="100%" viewBox="0 0 ' + totalWidth + ' ' + svgHeight + '" role="img" aria-label="' + escapeHtml(title) + '">';
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var y = i * (barHeight + gap);
      var barWidth = maxCount > 0 ? (item.count / maxCount) * chartWidth : 0;
      svg += '<text x="' + (labelWidth - 8) + '" y="' + (y + barHeight / 2 + 5) + '" text-anchor="end" font-size="13" fill="#333">' + escapeHtml(item.label) + '</text>';
      svg += '<rect x="' + labelWidth + '" y="' + y + '" width="' + barWidth + '" height="' + barHeight + '" rx="3" fill="' + color + '" opacity="0.85"/>';
      svg += '<text x="' + (labelWidth + barWidth + 6) + '" y="' + (y + barHeight / 2 + 5) + '" font-size="13" fill="#333">' + item.count + '</text>';
    }
    svg += '</svg>';

    return '<div class="detail-section"><h3 class="detail-section-title">' + escapeHtml(title) + '</h3><div class="detail-section-body">' + svg + '</div></div>';
  }

  function renderAboutPage() {
    var aboutHtml = '<div class="stats-page">';
    aboutHtml += '<h2 class="stats-title">About This App</h2>';
    aboutHtml += '<div class="about-body">';
    aboutHtml += '<p>V0.1 \u2014 This app is a much faster version of the fellows database. ';
    aboutHtml += 'This app is shared with EHF fellows on request on the condition that they keep the information in it private to the EHF fellows. ';
    aboutHtml += 'Never post this anywhere\u2014 it contains the relevant bits of data from the old fellows directory. ';
    aboutHtml += 'There is no API, login, or web app, so this can only be shared intentionally. ';
    aboutHtml += 'For support, request to join the github repository or just ask on one of the fellows channels.</p>';
    aboutHtml += '<p class="about-repo"><a href="https://github.com/richbodo/fellows_local_db" target="_blank" rel="noopener">';
    aboutHtml += '<svg class="github-icon" viewBox="0 0 16 16" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>';
    aboutHtml += ' richbodo/fellows_local_db</a></p>';
    aboutHtml += '</div>';

    aboutHtml += '<h2 class="stats-title">Fellowship Statistics</h2>';
    aboutHtml += '<p class="stats-total" id="stats-total">Loading stats\u2026</p>';
    aboutHtml += '<div class="stats-grid" id="stats-grid"></div>';
    aboutHtml += '</div>';
    detailEl.innerHTML = aboutHtml;

    fetch('/api/stats')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        var totalEl = document.getElementById('stats-total');
        var gridEl = document.getElementById('stats-grid');
        if (totalEl) totalEl.innerHTML = 'Total Fellows: <strong>' + escapeHtml(String(data.total)) + '</strong>';
        if (gridEl) {
          var gh = '<div class="stats-col stats-col--left">';
          gh += statsSection('Fellows by Type', data.by_fellow_type, '#4a2c6a');
          gh += statsSection('Fellows by Cohort', data.by_cohort, '#2c6a4a');
          gh += statsSection('Fellows by Region', data.by_region, '#2c4a6a');
          gh += '</div>';
          gh += '<div class="stats-col stats-col--right">';
          gh += statsSection('Field Completeness', data.field_completeness, '#5a5a5a');
          gh += '</div>';
          gridEl.innerHTML = gh;
        }
      })
      .catch(function () {
        var totalEl = document.getElementById('stats-total');
        if (totalEl) totalEl.textContent = 'Failed to load stats.';
      });
  }

  function route() {
    var hash = window.location.hash || '';
    if (hash === '#/about') {
      renderAboutPage();
    } else {
      updateDetailFromHash();
    }
  }

  function getSlugFromHash() {
    var hash = window.location.hash || '';
    var m = hash.match(/#\/fellow\/([^/]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function updateDetailFromHash() {
    var slug = getSlugFromHash();
    if (!slug) {
      renderDetail(null);
      return;
    }
    var fellow = fellowsBySlug.get(slug);
    if (fellow) {
      renderDetail(fellow);
      return;
    }
    detailEl.innerHTML = '<p class="placeholder">Loading…</p>';
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    fetch('/api/fellows/' + encodeURIComponent(slug))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data) fellowsBySlug.set(data.slug, data);
        if (getSlugFromHash() === slug) renderDetail(data);
      })
      .catch(function () {
        if (getSlugFromHash() === slug) renderDetail(null);
      });
  }

  // Phase 1: fetch list-only, render directory immediately (no images)
  fetch('/api/fellows')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      list = Array.isArray(data) ? data : [];
      renderDirectory();
      route();
      // Phase 2: full data in background
      fetch('/api/fellows?full=1')
        .then(function (r) { return r.json(); })
        .then(function (full) {
          if (Array.isArray(full)) {
            fullFellowsCache = full;
            saveFullFellowsToIndexedDB(full);
            full.forEach(function (f) {
              if (f.slug) fellowsBySlug.set(f.slug, f);
              if (f.record_id) fellowsBySlug.set(f.record_id, f);
            });
          }
          route();
        })
        .catch(function () {});
    })
    .catch(function () {
      loadingEl.textContent = 'Failed to load directory.';
    });

  window.addEventListener('hashchange', route);

  window.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'ArrowLeft') {
      var prev = detailEl.querySelector('.fellow-nav-arrow--prev:not(.fellow-nav-arrow--hidden)');
      if (prev) { e.preventDefault(); prev.click(); }
    } else if (e.key === 'ArrowRight') {
      var next = detailEl.querySelector('.fellow-nav-arrow--next:not(.fellow-nav-arrow--hidden)');
      if (next) { e.preventDefault(); next.click(); }
    }
  });

  function runSearch(q) {
    if (!q) {
      setSearchStatus('');
      renderDirectory();
      return;
    }
    if (!navigator.onLine) {
      setSearchStatus('Offline search (cached data)…');
      runLocalSearch(q);
      return;
    }
    setSearchStatus('Searching…');
    var url = '/api/search?q=' + encodeURIComponent(q);
    fetch(url)
      .then(function (r) {
        if (!r.ok) return [];
        return r.json();
      })
      .then(function (results) {
        if (!Array.isArray(results)) {
          results = [];
        }
        results.forEach(function (f) {
          if (f && f.slug) {
            fellowsBySlug.set(f.slug, f);
          }
          if (f && f.record_id) {
            fellowsBySlug.set(f.record_id, f);
          }
        });
        if (!results.length) {
          directoryListEl.innerHTML = '<p class="placeholder">No fellows match that search.</p>';
          setSearchStatus('');
        } else {
          renderDirectoryList(results);
          displayedList = results;
          setSearchStatus(results.length + ' result' + (results.length === 1 ? '' : 's') + ' found');
        }
      })
      .catch(function () {
        setSearchStatus('Network search failed. Trying cached data…');
        runLocalSearch(q);
      });
  }

  function runLocalSearch(q) {
    loadFullFellows().then(function (fellows) {
      if (!Array.isArray(fellows) || !fellows.length) {
        directoryListEl.innerHTML = '<p class="placeholder">No cached data available for offline search.</p>';
        setSearchStatus('');
        return;
      }
      var results = filterFellowsLocally(fellows, q);
      results.forEach(function (f) {
        if (f && f.slug) {
          fellowsBySlug.set(f.slug, f);
        }
        if (f && f.record_id) {
          fellowsBySlug.set(f.record_id, f);
        }
      });
      if (!results.length) {
        directoryListEl.innerHTML = '<p class="placeholder">No fellows match that search in cached data.</p>';
        setSearchStatus('');
      } else {
        renderDirectoryList(results);
        displayedList = results;
        setSearchStatus(results.length + ' offline result' + (results.length === 1 ? '' : 's') + ' found');
      }
    }).catch(function () {
      directoryListEl.innerHTML = '<p class="placeholder">Offline search failed.</p>';
      setSearchStatus('');
    });
  }

  function filterFellowsLocally(fellows, q) {
    var query = (q || '').toLowerCase();
    if (!query) return fellows.slice();
    var tokens = query.split(/\s+/).filter(Boolean);
    return fellows.filter(function (f) {
      var parts = [
        f.name,
        f.bio_tagline,
        f.cohort,
        f.fellow_type,
        f.search_tags,
        f.currently_based_in,
        f.global_regions_currently_based_in
      ];
      var haystack = parts
        .map(function (v) {
          return v == null ? '' : String(v).toLowerCase();
        })
        .join(' ');
      for (var i = 0; i < tokens.length; i++) {
        if (haystack.indexOf(tokens[i]) === -1) {
          return false;
        }
      }
      return true;
    });
  }

  function saveFullFellowsToIndexedDB(fellows) {
    if (!window.indexedDB || !Array.isArray(fellows)) return;
    var request = window.indexedDB.open('fellows-local-db', 1);
    request.onupgradeneeded = function (event) {
      var db = event.target.result;
      if (!db.objectStoreNames.contains('meta')) {
        db.createObjectStore('meta', { keyPath: 'id' });
      }
    };
    request.onsuccess = function (event) {
      var db = event.target.result;
      var tx = db.transaction('meta', 'readwrite');
      var store = tx.objectStore('meta');
      store.put({ id: 'allFellows', data: fellows });
      tx.oncomplete = function () {
        db.close();
      };
    };
    request.onerror = function () {
      // Ignore IndexedDB errors; app still works without offline cache.
    };
  }

  function loadFullFellows() {
    if (fullFellowsCache && Array.isArray(fullFellowsCache)) {
      return Promise.resolve(fullFellowsCache);
    }
    if (!window.indexedDB) {
      return Promise.resolve([]);
    }
    return new Promise(function (resolve, reject) {
      var request = window.indexedDB.open('fellows-local-db', 1);
      request.onupgradeneeded = function (event) {
        var db = event.target.result;
        if (!db.objectStoreNames.contains('meta')) {
          db.createObjectStore('meta', { keyPath: 'id' });
        }
      };
      request.onsuccess = function (event) {
        var db = event.target.result;
        var tx = db.transaction('meta', 'readonly');
        var store = tx.objectStore('meta');
        var getReq = store.get('allFellows');
        getReq.onsuccess = function () {
          var record = getReq.result;
          var data = record && Array.isArray(record.data) ? record.data : [];
          fullFellowsCache = data;
          resolve(data);
        };
        getReq.onerror = function () {
          resolve([]);
        };
        tx.oncomplete = function () {
          db.close();
        };
      };
      request.onerror = function () {
        resolve([]);
      };
    });
  }

  function handleSearchInput() {
    if (!searchInputEl) return;
    var raw = searchInputEl.value || '';
    var q = raw.trim();
    runSearch(q);
  }

  if (searchInputEl) {
    searchInputEl.addEventListener('input', function () {
      if (searchDebounceId) {
        clearTimeout(searchDebounceId);
      }
      searchDebounceId = setTimeout(function () {
        handleSearchInput();
      }, 250);
    });
  }

  function hasWindowAI() {
    return typeof window !== 'undefined' && window.ai;
  }

  function handleNlSearchClick() {
    if (!nlSearchInputEl) return;
    var query = (nlSearchInputEl.value || '').trim();
    if (!query) {
      setNlSearchStatus('Enter a question to search.');
      return;
    }
    if (!hasWindowAI()) {
      setNlSearchStatus('window.ai is not available in this browser.');
      return;
    }
    setNlSearchStatus('Asking model…');
    var prompt =
      'You help search a fellows directory stored in a SQLite FTS5 table named fellows_fts. ' +
      'Indexed columns include: name, bio_tagline, cohort, fellow_type, search_tags, key_links, ' +
      'currently_based_in, global_regions_currently_based_in. ' +
      'The user will describe who they are looking for in natural language. ' +
      'Your job is to translate this into a SINGLE MATCH string for SQLite FTS5 over those columns. ' +
      'Prefer combining short keywords with AND and OR. Do NOT return explanations, commentary, or code fences. ' +
      'Do NOT wrap the result in quotes. Return only the bare search string on the first line. ' +
      'Examples of valid outputs: Aaron; investor AND climate; cohort:2019 AND investor; "New Zealand" AND blockchain; women AND investor AND climate. ' +
      'User query: ' + query;

    try {
      var ai = window.ai;
      var generate = ai && ai.generateText ? ai.generateText.bind(ai) : null;
      if (!generate) {
        setNlSearchStatus('window.ai does not support text generation in this context.');
        return;
      }
      generate({
        prompt: prompt,
        maxTokens: 32,
        temperature: 0.2
      })
        .then(function (result) {
          var text = '';
          if (typeof result === 'string') {
            text = result;
          } else if (result && typeof result.text === 'string') {
            text = result.text;
          } else if (result && result.choices && result.choices[0] && typeof result.choices[0].text === 'string') {
            text = result.choices[0].text;
          }
          text = (text || '').trim();
          if (!text) {
            setNlSearchStatus('The model did not return a usable search string.');
            return;
          }
          var line = text.split('\n')[0];
          line = line.replace(/["']/g, '');
          if (line.length > 200) {
            line = line.slice(0, 200);
          }
          if (!line) {
            setNlSearchStatus('The model did not return a usable search string.');
            return;
          }
          setNlSearchStatus('Using search: ' + line);
          runSearch(line);
        })
        .catch(function () {
          setNlSearchStatus('Failed to get a response from window.ai.');
        });
    } catch (e) {
      setNlSearchStatus('Failed to use window.ai in this browser.');
    }
  }

  function initWindowAISearch() {
    if (!hasWindowAI()) return;
    if (nlSearchContainerEl) {
      nlSearchContainerEl.classList.remove('hidden');
    }
    if (nlSearchButtonEl) {
      nlSearchButtonEl.addEventListener('click', handleNlSearchClick);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWindowAISearch);
  } else {
    initWindowAISearch();
  }

  function updateConnectionBanner() {
    if (!connectionBannerEl) return;
    if (navigator.onLine) {
      connectionBannerEl.textContent = 'You are online.';
      connectionBannerEl.classList.remove('hidden');
      setTimeout(function () {
        connectionBannerEl.classList.add('hidden');
      }, 2000);
    } else {
      connectionBannerEl.textContent = 'You are offline. Showing cached data where available.';
      connectionBannerEl.classList.remove('hidden');
    }
  }

  window.addEventListener('online', updateConnectionBanner);
  window.addEventListener('offline', updateConnectionBanner);
  updateConnectionBanner();

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker
        .register('/sw.js')
        .catch(function () {
          // Ignore registration errors; app still works without PWA features.
        });
    });
  }
})();
