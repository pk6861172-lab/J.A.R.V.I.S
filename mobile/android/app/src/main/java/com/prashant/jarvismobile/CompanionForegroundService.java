package com.prashant.jarvismobile;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.media.Image;
import android.media.ImageReader;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Environment;
import android.util.Base64;
import android.util.Size;
import android.view.Surface;

import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONObject;
import org.json.JSONArray;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class CompanionForegroundService extends Service {
    public static final String ACTION_START = "com.prashant.jarvismobile.companion.START";
    public static final String ACTION_STOP = "com.prashant.jarvismobile.companion.STOP";
    private static final String CHANNEL_ID = "jarvis_companion_live";
    private static final int NOTIFICATION_ID = 9117;

    private static volatile boolean running = false;

    private SharedPreferences prefs;
    private HandlerThread workerThread;
    private Handler worker;
    private CameraDevice cameraDevice;
    private CameraCaptureSession cameraSession;
    private ImageReader imageReader;
    private long lastFrameSentAt = 0L;
    private MediaRecorder recorder;
    private File audioFile;
    private boolean audioRestarting = false;
    private long lastFileSyncMtime = 0L;
    private final Runnable fileSyncRunnable = new Runnable() {
        @Override
        public void run() {
            if (!running) return;
            if (prefs.getBoolean("file_sync_enabled", false) && hasAllFilesAccess()) {
                syncFilesOnce();
            }
            if (running) worker.postDelayed(this, 60000);
        }
    };
    private LocationManager locationManager;
    private final LocationListener locationListener = new LocationListener() {
        @Override
        public void onLocationChanged(Location location) {
            sendLocation(location);
        }

        @Override public void onStatusChanged(String provider, int status, Bundle extras) {}
        @Override public void onProviderEnabled(String provider) {}
        @Override public void onProviderDisabled(String provider) {}
    };

    public static boolean isRunning() {
        return running;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("jarvis_mobile", Context.MODE_PRIVATE);
        workerThread = new HandlerThread("JarvisCompanionLive");
        workerThread.start();
        worker = new Handler(workerThread.getLooper());
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null ? "" : intent.getAction();
        if (ACTION_STOP.equals(action)) {
            stopLiveSharing();
            stopSelf();
            return START_NOT_STICKY;
        }
        startForeground(NOTIFICATION_ID, buildNotification("Starting live sharing..."));
        running = true;
        worker.post(this::startLiveSharing);
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        stopLiveSharing();
        if (workerThread != null) {
            workerThread.quitSafely();
        }
        super.onDestroy();
    }

    @Override
    public android.os.IBinder onBind(Intent intent) {
        return null;
    }

    private void startLiveSharing() {
        postSession("connected");
        startLocationUpdates();
        startAudioLoop();
        startCameraLoop();
        startFileSyncLoop();
        updateNotification(prefs.getBoolean("file_sync_enabled", false)
                ? "Sharing camera, microphone, location, and selected file index"
                : "Sharing camera, microphone, and location");
    }

    private void stopLiveSharing() {
        running = false;
        stopCameraLoop();
        stopAudioLoop(true);
        stopLocationUpdates();
        stopFileSyncLoop();
        postSession("disconnected");
        stopForeground(true);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "JARVIS live companion",
                NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription("Visible status while JARVIS receives phone camera, mic, and location.");
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.createNotificationChannel(channel);
    }

    private Notification buildNotification(String text) {
        Intent stopIntent = new Intent(this, CompanionForegroundService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPending = PendingIntent.getService(
                this,
                42,
                stopIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        Intent openIntent = new Intent(this, MainActivity.class);
        PendingIntent openPending = PendingIntent.getActivity(
                this,
                43,
                openIntent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );

        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.presence_video_online)
                .setContentTitle("JARVIS companion is live")
                .setContentText(text)
                .setOngoing(true)
                .setContentIntent(openPending)
                .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Disconnect", stopPending)
                .build();
    }

    private void updateNotification(String text) {
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) manager.notify(NOTIFICATION_ID, buildNotification(text));
    }

    private String serverUrl() {
        String value = prefs.getString("server_url", "");
        if (value == null) return "";
        value = value.trim();
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        return value;
    }

    private String apiToken() {
        String value = prefs.getString("api_token", "");
        return value == null ? "" : value.trim();
    }

    private boolean hasPermission(String permission) {
        return ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean hasAllFilesAccess() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager();
    }

    private void postSession(String status) {
        try {
            JSONObject json = new JSONObject();
            json.put("status", status);
            json.put(status.equals("connected") ? "connected_at" : "disconnected_at", isoNow());
            postJson("/api/mobile/session", json);
        } catch (Exception ignored) {}
    }

    private void startLocationUpdates() {
        if (!hasPermission(Manifest.permission.ACCESS_FINE_LOCATION) && !hasPermission(Manifest.permission.ACCESS_COARSE_LOCATION)) {
            return;
        }
        try {
            locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
            if (locationManager == null) return;
            if (hasPermission(Manifest.permission.ACCESS_FINE_LOCATION)) {
                locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 5000, 4f, locationListener, worker.getLooper());
            }
            locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 5000, 4f, locationListener, worker.getLooper());
        } catch (Exception ignored) {}
    }

    private void stopLocationUpdates() {
        try {
            if (locationManager != null) locationManager.removeUpdates(locationListener);
        } catch (Exception ignored) {}
        locationManager = null;
    }

    private void sendLocation(Location location) {
        if (!running || location == null) return;
        try {
            JSONObject json = new JSONObject();
            json.put("latitude", location.getLatitude());
            json.put("longitude", location.getLongitude());
            json.put("accuracy_m", location.hasAccuracy() ? location.getAccuracy() : JSONObject.NULL);
            json.put("altitude_m", location.hasAltitude() ? location.getAltitude() : JSONObject.NULL);
            json.put("speed_mps", location.hasSpeed() ? location.getSpeed() : JSONObject.NULL);
            json.put("heading_deg", location.hasBearing() ? location.getBearing() : JSONObject.NULL);
            json.put("captured_at", isoNow());
            postJson("/api/mobile/location", json);
        } catch (Exception ignored) {}
    }

    private void startAudioLoop() {
        if (!hasPermission(Manifest.permission.RECORD_AUDIO) || !running) return;
        worker.post(this::recordAudioChunk);
    }

    private void recordAudioChunk() {
        if (!running || audioRestarting) return;
        try {
            audioFile = File.createTempFile("jarvis_audio_", ".m4a", getCacheDir());
            recorder = new MediaRecorder();
            recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
            recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            recorder.setAudioEncodingBitRate(64000);
            recorder.setAudioSamplingRate(16000);
            recorder.setOutputFile(audioFile.getAbsolutePath());
            recorder.prepare();
            recorder.start();
            worker.postDelayed(() -> stopAudioLoop(false), 3000);
        } catch (Exception exc) {
            stopAudioLoop(true);
        }
    }

    private void stopAudioLoop(boolean finalStop) {
        File finished = audioFile;
        try {
            if (recorder != null) {
                recorder.stop();
            }
        } catch (Exception ignored) {
        } finally {
            try {
                if (recorder != null) recorder.release();
            } catch (Exception ignored) {}
            recorder = null;
            audioFile = null;
        }
        if (finished != null && finished.exists() && finished.length() > 0 && running) {
            sendAudioFile(finished);
        }
        if (finished != null) {
            try { finished.delete(); } catch (Exception ignored) {}
        }
        if (!finalStop && running) {
            audioRestarting = true;
            worker.postDelayed(() -> {
                audioRestarting = false;
                recordAudioChunk();
            }, 600);
        }
    }

    private void sendAudioFile(File file) {
        try {
            byte[] bytes = readBytes(file);
            JSONObject json = new JSONObject();
            json.put("audio", "data:audio/mp4;base64," + Base64.encodeToString(bytes, Base64.NO_WRAP));
            json.put("mime_type", "audio/mp4");
            json.put("captured_at", isoNow());
            postJson("/api/mobile/audio", json);
        } catch (Exception ignored) {}
    }

    private void startCameraLoop() {
        if (!hasPermission(Manifest.permission.CAMERA) || !running) return;
        try {
            CameraManager manager = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
            if (manager == null) return;
            String cameraId = chooseCamera(manager);
            if (cameraId == null) return;
            imageReader = ImageReader.newInstance(640, 480, ImageFormat.JPEG, 2);
            imageReader.setOnImageAvailableListener(reader -> {
                Image image = null;
                try {
                    image = reader.acquireLatestImage();
                    if (image == null || !running) return;
                    long now = System.currentTimeMillis();
                    if (now - lastFrameSentAt < 1500) return;
                    lastFrameSentAt = now;
                    ByteBuffer buffer = image.getPlanes()[0].getBuffer();
                    byte[] bytes = new byte[buffer.remaining()];
                    buffer.get(bytes);
                    sendFrame(bytes);
                } catch (Exception ignored) {
                } finally {
                    if (image != null) image.close();
                }
            }, worker);
            manager.openCamera(cameraId, new CameraDevice.StateCallback() {
                @Override
                public void onOpened(CameraDevice camera) {
                    cameraDevice = camera;
                    createCameraSession();
                }

                @Override public void onDisconnected(CameraDevice camera) { camera.close(); }
                @Override public void onError(CameraDevice camera, int error) { camera.close(); }
            }, worker);
        } catch (Exception ignored) {}
    }

    private String chooseCamera(CameraManager manager) throws CameraAccessException {
        String first = null;
        for (String id : manager.getCameraIdList()) {
            if (first == null) first = id;
            CameraCharacteristics c = manager.getCameraCharacteristics(id);
            Integer facing = c.get(CameraCharacteristics.LENS_FACING);
            if (facing != null && facing == CameraCharacteristics.LENS_FACING_BACK) return id;
        }
        return first;
    }

    private void createCameraSession() {
        try {
            if (cameraDevice == null || imageReader == null) return;
            Surface surface = imageReader.getSurface();
            CaptureRequest.Builder request = cameraDevice.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
            request.addTarget(surface);
            cameraDevice.createCaptureSession(Arrays.asList(surface), new CameraCaptureSession.StateCallback() {
                @Override
                public void onConfigured(CameraCaptureSession session) {
                    cameraSession = session;
                    try {
                        session.setRepeatingRequest(request.build(), null, worker);
                    } catch (Exception ignored) {}
                }

                @Override public void onConfigureFailed(CameraCaptureSession session) {}
            }, worker);
        } catch (Exception ignored) {}
    }

    private void stopCameraLoop() {
        try { if (cameraSession != null) cameraSession.close(); } catch (Exception ignored) {}
        try { if (cameraDevice != null) cameraDevice.close(); } catch (Exception ignored) {}
        try { if (imageReader != null) imageReader.close(); } catch (Exception ignored) {}
        cameraSession = null;
        cameraDevice = null;
        imageReader = null;
    }

    private void sendFrame(byte[] bytes) {
        try {
            JSONObject json = new JSONObject();
            json.put("image", "data:image/jpeg;base64," + Base64.encodeToString(bytes, Base64.NO_WRAP));
            json.put("width", 640);
            json.put("height", 480);
            json.put("captured_at", isoNow());
            postJson("/api/mobile/frame", json);
        } catch (Exception ignored) {}
    }

    private void startFileSyncLoop() {
        if (!prefs.getBoolean("file_sync_enabled", false) || !hasAllFilesAccess()) return;
        worker.post(fileSyncRunnable);
    }

    private void stopFileSyncLoop() {
        if (worker != null) worker.removeCallbacks(fileSyncRunnable);
    }

    private void syncFilesOnce() {
        try {
            List<File> files = new ArrayList<>();
            File root = Environment.getExternalStorageDirectory();
            String[] roots = new String[] {
                    "Download", "Downloads", "DCIM", "Documents", "Pictures", "Movies", "Music",
                    "WhatsApp/Media", "Android/media/com.whatsapp/WhatsApp/Media"
            };
            for (String name : roots) {
                collectFiles(new File(root, name), files, 0);
            }
            files.sort(Comparator.comparingLong(File::lastModified).reversed());

            JSONArray index = new JSONArray();
            int count = 0;
            long newest = lastFileSyncMtime;
            int uploaded = 0;
            for (File file : files) {
                if (count >= 500) break;
                JSONObject item = new JSONObject();
                item.put("name", file.getName());
                item.put("path", safeRelativePath(root, file));
                item.put("bytes", file.length());
                item.put("modified_at", file.lastModified());
                index.put(item);
                count++;
                newest = Math.max(newest, file.lastModified());

                if (uploaded < 5 && file.lastModified() > lastFileSyncMtime && file.length() > 0 && file.length() <= 8_000_000) {
                    uploadFile(root, file);
                    uploaded++;
                }
            }

            JSONObject payload = new JSONObject();
            payload.put("indexed_at", isoNow());
            payload.put("root", root.getAbsolutePath());
            payload.put("file_count", count);
            payload.put("uploaded_recent_files", uploaded);
            payload.put("files", index);
            postJson("/api/mobile/file_index", payload);
            if (newest > lastFileSyncMtime) {
                lastFileSyncMtime = newest;
            }
        } catch (Exception ignored) {}
    }

    private void collectFiles(File dir, List<File> out, int depth) {
        if (dir == null || !dir.exists() || !dir.canRead() || depth > 4 || out.size() >= 1200) return;
        File[] children = dir.listFiles();
        if (children == null) return;
        for (File child : children) {
            if (out.size() >= 1200) return;
            if (child.isDirectory()) {
                collectFiles(child, out, depth + 1);
            } else if (child.isFile()) {
                out.add(child);
            }
        }
    }

    private String safeRelativePath(File root, File file) {
        try {
            String rootPath = root.getCanonicalPath();
            String filePath = file.getCanonicalPath();
            if (filePath.startsWith(rootPath)) {
                return filePath.substring(rootPath.length()).replace("\\", "/").replaceFirst("^/+", "");
            }
        } catch (Exception ignored) {}
        return file.getName();
    }

    private void uploadFile(File root, File file) {
        try {
            JSONObject json = new JSONObject();
            json.put("relative_path", safeRelativePath(root, file));
            json.put("name", file.getName());
            json.put("bytes", file.length());
            json.put("modified_at", file.lastModified());
            json.put("content", "data:application/octet-stream;base64," + Base64.encodeToString(readBytes(file), Base64.NO_WRAP));
            postJson("/api/mobile/file", json);
        } catch (Exception ignored) {}
    }

    private void postJson(String path, JSONObject json) throws IOException {
        String base = serverUrl();
        if (base.isEmpty()) return;
        URL url = new URL(base + path);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(8000);
        conn.setReadTimeout(12000);
        conn.setRequestMethod("POST");
        conn.setDoOutput(true);
        conn.setRequestProperty("Content-Type", "application/json");
        conn.setRequestProperty("X-Jarvis-Token", apiToken());
        byte[] body = json.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        conn.setFixedLengthStreamingMode(body.length);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(body);
        }
        try {
            conn.getResponseCode();
        } finally {
            conn.disconnect();
        }
    }

    private byte[] readBytes(File file) throws IOException {
        try (FileInputStream in = new FileInputStream(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }

    private String isoNow() {
        return String.format(Locale.ROOT, "%tFT%<tTZ", System.currentTimeMillis());
    }
}
