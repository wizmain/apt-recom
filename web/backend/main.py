"""FastAPI backend for apartment recommendation app."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from routers import apartments, nudge, detail, chat, knowledge, commute, feedback, dashboard, codes, similar, admin

app = FastAPI(title="Apartment Recommendation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apartments.router, prefix="/api")
app.include_router(nudge.router, prefix="/api")
app.include_router(detail.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(commute.router, prefix="/api")
app.include_router(feedback.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(codes.router, prefix="/api")
app.include_router(similar.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


KAKAO_MAP_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 100%; height: 100%; overflow: hidden; }
  #map { width: 100%; height: 100%; }
  #status { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
    font-family: -apple-system, sans-serif; color: #6B7280; font-size: 14px; text-align: center; }
</style>
</head><body>
<div id="map"></div>
<div id="status">지도 로딩 중...</div>
<script>
  window.onerror = function(msg, url, line) {
    document.getElementById('status').innerText = 'JS Error: ' + msg;
    document.getElementById('status').style.color = '#EF4444';
    try { window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'error', message: msg })); } catch(e) {}
    return true;
  };
</script>
<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey=832af9764dadaf139a8e82517d49e9f3&libraries=clusterer&autoload=false"
  onerror="document.getElementById('status').innerText='SDK 로드 실패';document.getElementById('status').style.color='#EF4444';try{window.ReactNativeWebView.postMessage(JSON.stringify({type:'error',message:'SDK script load failed'}))}catch(e){}"></script>
<script>
  if (typeof kakao === 'undefined' || !kakao.maps) {
    document.getElementById('status').innerText = 'kakao 객체 없음 - SDK 로드 실패';
    document.getElementById('status').style.color = '#EF4444';
    try { window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'error', message: 'kakao undefined' })); } catch(e) {}
  } else {
  kakao.maps.load(function() {
    document.getElementById('status').style.display = 'none';
    var container = document.getElementById('map');
    var map = new kakao.maps.Map(container, {
      center: new kakao.maps.LatLng(37.5665, 126.978),
      level: 8,
    });
    window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'mapReady' }));

    var basicOverlays = [];
    var scoredOverlays = [];
    var infowindow = null;

    function clearBasicMarkers() {
      basicOverlays.forEach(function(m) { m.setMap(null); });
      basicOverlays = [];
    }
    function clearScoredMarkers() {
      scoredOverlays.forEach(function(m) { m.setMap(null); });
      scoredOverlays = [];
      if (infowindow) infowindow.close();
    }

    function getRankColor(rank) {
      if (rank === 1) return '#EF4444';
      if (rank === 2) return '#F97316';
      if (rank === 3) return '#EC4899';
      return '#3B82F6';
    }

    /* 일반 아파트 마커 (작은 회색 점) */
    function addBasicMarkers(apts, shouldFocus) {
      clearBasicMarkers();
      apts.forEach(function(apt) {
        var el = document.createElement('div');
        el.style.cssText = 'width:10px;height:10px;border-radius:50%;background:#6B7280;border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.2);cursor:pointer;';
        var overlay = new kakao.maps.CustomOverlay({
          position: new kakao.maps.LatLng(apt.lat, apt.lng),
          content: el, yAnchor: 0.5,
        });
        overlay.setMap(map);
        basicOverlays.push(overlay);
        el.addEventListener('click', function() {
          if (infowindow) infowindow.close();
          var iw = new kakao.maps.InfoWindow({
            content: '<div style="padding:6px 10px;font-size:12px;background:#fff;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.15);"><b>' + apt.name + '</b></div>',
            position: new kakao.maps.LatLng(apt.lat, apt.lng),
          });
          iw.open(map);
          infowindow = iw;
          window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'aptClick', pnu: apt.pnu }));
        });
      });
      if (shouldFocus && apts.length > 0) {
        var bounds = new kakao.maps.LatLngBounds();
        apts.forEach(function(a) { bounds.extend(new kakao.maps.LatLng(a.lat, a.lng)); });
        map.setBounds(bounds, 80);
      }
    }

    /* 스코어링 마커 (컬러 원형 랭킹) */
    function addScoredMarkers(apts) {
      clearScoredMarkers();
      apts.forEach(function(apt) {
        var el = document.createElement('div');
        el.style.cssText = 'width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:bold;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);background:' + getRankColor(apt.rank);
        el.innerText = apt.rank;
        var overlay = new kakao.maps.CustomOverlay({
          position: new kakao.maps.LatLng(apt.lat, apt.lng),
          content: el, yAnchor: 0.5,
        });
        overlay.setMap(map);
        scoredOverlays.push(overlay);
        el.addEventListener('click', function() {
          if (infowindow) infowindow.close();
          var iw = new kakao.maps.InfoWindow({
            content: '<div style="padding:8px 12px;font-size:13px;min-width:150px;background:#fff;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.15);"><b>' + apt.name + '</b><br><span style="color:#3B82F6;font-weight:bold;">' + apt.score.toFixed(1) + '점</span></div>',
            position: new kakao.maps.LatLng(apt.lat, apt.lng),
          });
          iw.open(map);
          infowindow = iw;
          window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'aptClick', pnu: apt.pnu }));
        });
      });
      if (apts.length > 0) {
        var bounds = new kakao.maps.LatLngBounds();
        apts.forEach(function(a) { bounds.extend(new kakao.maps.LatLng(a.lat, a.lng)); });
        map.setBounds(bounds, 80);
      }
    }

    /* 챗봇 하이라이트 마커 (빨간 핀 + 이름 라벨) */
    var highlightOverlays = [];
    function clearHighlightMarkers() {
      highlightOverlays.forEach(function(m) { m.setMap(null); });
      highlightOverlays = [];
      if (infowindow) { infowindow.close(); infowindow = null; }
    }
    function addHighlightMarkers(apts) {
      clearHighlightMarkers();
      apts.forEach(function(apt) {
        var wrap = document.createElement('div');
        wrap.style.cssText = 'display:flex;flex-direction:column;align-items:center;cursor:pointer;';
        var label = document.createElement('div');
        label.style.cssText = 'background:#fff;border:1px solid #DC2626;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:bold;color:#DC2626;margin-bottom:4px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,0.12);';
        label.innerText = apt.name;
        var dot = document.createElement('div');
        dot.style.cssText = 'width:12px;height:12px;border-radius:50%;background:#DC2626;border:2px solid #fff;box-shadow:0 0 6px rgba(220,38,38,0.4);';
        wrap.appendChild(label);
        wrap.appendChild(dot);
        var overlay = new kakao.maps.CustomOverlay({
          position: new kakao.maps.LatLng(apt.lat, apt.lng),
          content: wrap, yAnchor: 1,
        });
        overlay.setMap(map);
        highlightOverlays.push(overlay);
        wrap.addEventListener('click', function() {
          if (infowindow) { infowindow.close(); infowindow = null; }
          window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'aptClick', pnu: apt.pnu }));
        });
      });
      if (apts.length > 0) {
        var bounds = new kakao.maps.LatLngBounds();
        apts.forEach(function(a) { bounds.extend(new kakao.maps.LatLng(a.lat, a.lng)); });
        map.setBounds(bounds, 80);
      }
    }

    function handleMessage(e) {
      try {
        var msg = JSON.parse(e.data);
        if (msg.type === 'updateBasicMarkers') addBasicMarkers(msg.markers, msg.focus);
        if (msg.type === 'updateScoredMarkers') addScoredMarkers(msg.markers);
        if (msg.type === 'clearScoredMarkers') clearScoredMarkers();
        if (msg.type === 'updateHighlightMarkers') addHighlightMarkers(msg.markers);
        if (msg.type === 'clearHighlightMarkers') clearHighlightMarkers();
        if (msg.type === 'moveTo') {
          map.setCenter(new kakao.maps.LatLng(msg.lat, msg.lng));
          map.setLevel(msg.level || 5);
        }
      } catch(err) {}
    }
    window.addEventListener('message', handleMessage);
    document.addEventListener('message', handleMessage);
    kakao.maps.event.addListener(map, 'idle', function() {
      var b = map.getBounds();
      var sw = b.getSouthWest();
      var ne = b.getNorthEast();
      window.ReactNativeWebView.postMessage(JSON.stringify({
        type: 'boundsChanged',
        sw: { lat: sw.getLat(), lng: sw.getLng() },
        ne: { lat: ne.getLat(), lng: ne.getLng() },
      }));
    });
  });
  }
</script>
</body></html>"""


@app.get("/api/map", response_class=HTMLResponse)
def map_page():
    """모바일 앱 WebView용 카카오맵 HTML 페이지."""
    return KAKAO_MAP_HTML


# ── Admin SPA 정적 파일 서빙 ──────────────────────────────────

_ADMIN_STATIC_DIR = Path(__file__).resolve().parent / "static" / "admin"

if _ADMIN_STATIC_DIR.is_dir():
    app.mount(
        "/admin/assets",
        StaticFiles(directory=str(_ADMIN_STATIC_DIR / "assets")),
        name="admin-assets",
    )

    @app.get("/admin/{path:path}")
    async def admin_spa_fallback(path: str = ""):
        """React Router SPA fallback — /admin/* 경로를 index.html로."""
        index = _ADMIN_STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return HTMLResponse("Admin not built", status_code=404)

    @app.get("/admin")
    async def admin_root():
        """관리자 페이지 루트."""
        index = _ADMIN_STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return HTMLResponse("Admin not built", status_code=404)
