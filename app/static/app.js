// EHF Fellows directory – two-phase load: list first, then full data in background.
// Detail layout matches reference: table-like rows, purple/grey section headers, two columns.

(function () {
  var DETAIL_PAGE_TITLE = 'Confidential - Fellows Local-Only Directory Development Project';
  var fellowsBySlug = new Map();
  var list = [];
  var loadingEl = document.getElementById('loading');
  var appWrapEl = document.getElementById('app-wrap');
  var directoryEl = document.getElementById('directory');
  var detailEl = document.getElementById('detail');

  function showLoading(show) {
    loadingEl.classList.toggle('hidden', !show);
  }

  function showApp(show) {
    if (appWrapEl) appWrapEl.classList.toggle('hidden', !show);
  }

  function renderDirectory() {
    var ul = document.createElement('ul');
    list.forEach(function (f) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = '#/fellow/' + encodeURIComponent(f.slug || '');
      var displayName = (f.name && String(f.name).trim()) ? f.name : 'Unknown';
      a.textContent = displayName;
      li.appendChild(a);
      ul.appendChild(li);
    });
    directoryEl.innerHTML = '';
    directoryEl.appendChild(ul);
    showLoading(false);
    showApp(true);
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
    workRows.push(workBlock('What is your main mode of working?', fellow.what_is_your_main_mode_of_working));
    workRows.push(workBlock('Do you consider yourself an investor in one or more of these categories?', fellow.do_you_consider_yourself_an_investor_in_one_or_more_of_these_categories));
    workRows.push(workBlock('What are the main types of organisations you serve?', fellow.what_are_the_main_types_of_organisations_you_serve));
    var workBody = workRows.join('');
    var rightTop = section('Work', workBody);

    var rightRest = '';
    rightRest += sectionAlways('Career Highlights', fellow.career_highlights ? escapeHtml(fellow.career_highlights) : '', true);
    rightRest += sectionAlways("How I'm looking to support the NZ ecosystem", fellow.how_im_looking_to_support_the_nz_ecosystem ? escapeHtml(fellow.how_im_looking_to_support_the_nz_ecosystem) : '', true);
    rightRest += sectionAlways('Key Networks', fellow.key_networks ? escapeHtml(fellow.key_networks) : '', true);

    var html = '<header class="detail-page-title">' + escapeHtml(DETAIL_PAGE_TITLE) + '</header>' +
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
      updateDetailFromHash();
      // Phase 2: full data in background
      fetch('/api/fellows?full=1')
        .then(function (r) { return r.json(); })
        .then(function (full) {
          if (Array.isArray(full)) {
            full.forEach(function (f) {
              if (f.slug) fellowsBySlug.set(f.slug, f);
              if (f.record_id) fellowsBySlug.set(f.record_id, f);
            });
          }
          updateDetailFromHash();
        })
        .catch(function () {});
    })
    .catch(function () {
      loadingEl.textContent = 'Failed to load directory.';
    });

  window.addEventListener('hashchange', updateDetailFromHash);
})();
