import Foundation
import AVFoundation
import ScreenCaptureKit
import CoreMedia

// MARK: - Args
// Usage: recorder <system_audio.wav> <duration_seconds|0> <internal|microphone|both>
//   output path = path to system audio WAV; mic path derived as <stem>_mic.wav
//   duration = 0 means record until SIGINT

struct Config {
    let sysWavPath: String
    let micWavPath: String
    let duration: Double?
    enum Mode { case sysOnly, micOnly, both }
    let mode: Mode
}

func parseArgs() -> Config {
    let args = CommandLine.arguments
    guard args.count >= 4 else {
        fputs("Usage: recorder <output.wav> <duration_seconds|0> <internal|microphone|both>\n", stderr)
        exit(1)
    }
    let sysPath = args[1]
    let dur = Double(args[2]).flatMap { $0 > 0 ? $0 : nil }
    let url = URL(fileURLWithPath: sysPath)
    let micPath = url.deletingLastPathComponent()
        .appendingPathComponent(url.deletingPathExtension().lastPathComponent + "_mic")
        .appendingPathExtension("wav").path
    let mode: Config.Mode
    switch args[3] {
    case "internal":   mode = .sysOnly
    case "microphone": mode = .micOnly
    default:           mode = .both
    }
    return Config(sysWavPath: sysPath, micWavPath: micPath, duration: dur, mode: mode)
}

// MARK: - WAV Writer (AVAssetWriter)

final class AssetWAVWriter {
    private var assetWriter: AVAssetWriter
    private var writerInput: AVAssetWriterInput

    init(url: URL, sampleRate: Double, channels: Int) throws {
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: channels,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false
        ]
        assetWriter = try AVAssetWriter(outputURL: url, fileType: .wav)
        writerInput = AVAssetWriterInput(mediaType: .audio, outputSettings: settings)
        writerInput.expectsMediaDataInRealTime = true
        assetWriter.add(writerInput)
        assetWriter.startWriting()
        assetWriter.startSession(atSourceTime: .zero)
    }

    func append(_ sampleBuffer: CMSampleBuffer) {
        guard writerInput.isReadyForMoreMediaData else { return }
        writerInput.append(sampleBuffer)
    }

    func finish(completion: @escaping () -> Void) {
        writerInput.markAsFinished()
        assetWriter.finishWriting(completionHandler: completion)
    }
}

// MARK: - Microphone Recorder

final class MicRecorder {
    private let engine = AVAudioEngine()
    private var file: AVAudioFile?
    private let outputURL: URL

    init(outputURL: URL) {
        self.outputURL = outputURL
    }

    func start() throws {
        let inputNode = engine.inputNode
        let inputFmt = inputNode.outputFormat(forBus: 0)

        let writeFmt = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                     sampleRate: 48000, channels: 1, interleaved: false)!

        let wavSettings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 48000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false
        ]
        file = try AVAudioFile(forWriting: outputURL, settings: wavSettings,
                               commonFormat: .pcmFormatInt16, interleaved: true)

        guard let converter = AVAudioConverter(from: inputFmt, to: writeFmt) else {
            throw NSError(domain: "MicRecorder", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Cannot create audio converter"])
        }

        inputNode.installTap(onBus: 0, bufferSize: 4096, format: inputFmt) { [weak self] buf, _ in
            guard let self = self else { return }
            let outFrames = AVAudioFrameCount(
                Double(buf.frameLength) * writeFmt.sampleRate / inputFmt.sampleRate) + 1
            guard let outBuf = AVAudioPCMBuffer(pcmFormat: writeFmt, frameCapacity: outFrames) else { return }
            var filled = false
            converter.convert(to: outBuf, error: nil) { _, status in
                if !filled { filled = true; status.pointee = .haveData; return buf }
                status.pointee = .noDataNow; return nil
            }
            // Convert float32 → int16
            guard outBuf.frameLength > 0,
                  let floatPtr = outBuf.floatChannelData else { return }
            let int16Fmt = AVAudioFormat(commonFormat: .pcmFormatInt16,
                                         sampleRate: 48000, channels: 1, interleaved: true)!
            guard let intBuf = AVAudioPCMBuffer(pcmFormat: int16Fmt, frameCapacity: outBuf.frameLength),
                  let intPtr = intBuf.int16ChannelData else { return }
            intBuf.frameLength = outBuf.frameLength
            let n = Int(outBuf.frameLength)
            for i in 0..<n {
                let v = max(-1.0, min(1.0, floatPtr[0][i]))
                intPtr[0][i] = Int16(v * 32767.0)
            }
            try? self.file?.write(from: intBuf)
        }

        try engine.start()
        print("[mic] Recording → \(outputURL.lastPathComponent)")
    }

    func stop() {
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        file = nil
        print("[mic] Saved → \(outputURL.lastPathComponent)")
    }
}

// MARK: - System Audio Recorder (ScreenCaptureKit)

@available(macOS 12.3, *)
final class SysAudioRecorder: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private var writer: AssetWAVWriter?
    private let outputURL: URL
    private var startTime: CMTime?

    init(outputURL: URL) { self.outputURL = outputURL }

    func setup() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            throw NSError(domain: "SysAudio", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "No display found"])
        }

        let filter = SCContentFilter(display: display,
                                      excludingApplications: [],
                                      exceptingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true
        cfg.excludesCurrentProcessAudio = true
        cfg.sampleRate = 48000
        cfg.channelCount = 2
        // Minimal video so we're not wasting CPU
        cfg.width = 2; cfg.height = 2
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)

        stream = SCStream(filter: filter, configuration: cfg, delegate: self)
        try stream!.addStreamOutput(self, type: .audio,
                                    sampleHandlerQueue: DispatchQueue(label: "sysaudio.q"))
        writer = try AssetWAVWriter(url: outputURL, sampleRate: 48000, channels: 2)
    }

    func start() async throws {
        try await stream?.startCapture()
        print("[sys] Recording → \(outputURL.lastPathComponent)")
    }

    func stop(completion: @escaping () -> Void) {
        stream?.stopCapture { [weak self] _ in
            self?.stream = nil
            self?.writer?.finish {
                print("[sys] Saved → \(self?.outputURL.lastPathComponent ?? "")")
                completion()
            }
        }
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer buf: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }
        if startTime == nil { startTime = buf.presentationTimeStamp }
        guard let writer = writer else { return }

        // Retime to start from zero
        if let t0 = startTime,
           let retimedBuf = retime(buf, offsetBy: t0) {
            writer.append(retimedBuf)
        } else {
            writer.append(buf)
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        fputs("[sys] Stream stopped with error: \(error)\n", stderr)
    }

    private func retime(_ buf: CMSampleBuffer, offsetBy t0: CMTime) -> CMSampleBuffer? {
        let pts = CMTimeSubtract(buf.presentationTimeStamp, t0)
        var timing = CMSampleTimingInfo(duration: buf.duration,
                                         presentationTimeStamp: pts,
                                         decodeTimeStamp: .invalid)
        var newBuf: CMSampleBuffer?
        CMSampleBufferCreateCopyWithNewTiming(allocator: nil, sampleBuffer: buf,
                                              sampleTimingEntryCount: 1, sampleTimingArray: &timing,
                                              sampleBufferOut: &newBuf)
        return newBuf
    }
}

// MARK: - Main

let cfg = parseArgs()
let outputDir = URL(fileURLWithPath: cfg.sysWavPath).deletingLastPathComponent()
try? FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)

print("Meeting Recorder starting — mode: \(cfg.mode)")
print("System audio → \(cfg.sysWavPath)")
if cfg.mode == .micOnly || cfg.mode == .both {
    print("Microphone   → \(cfg.micWavPath)")
}
print("Press Ctrl+C to stop.\n")

if #available(macOS 12.3, *) {
    var micRec: MicRecorder?
    var sysRec: SysAudioRecorder?

    // Signal handler for graceful shutdown
    let sigSrc = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
    signal(SIGINT, SIG_IGN)

    sigSrc.setEventHandler {
        print("\nShutting down...")
        let group = DispatchGroup()

        micRec?.stop()

        if let s = sysRec {
            group.enter()
            s.stop { group.leave() }
        }

        group.notify(queue: .main) {
            print("Done.")
            exit(0)
        }
    }
    sigSrc.resume()

    // Duration auto-stop
    if let dur = cfg.duration {
        DispatchQueue.main.asyncAfter(deadline: .now() + dur) {
            print("\nDuration \(dur)s reached. Shutting down...")
            let group = DispatchGroup()
            micRec?.stop()
            if let s = sysRec {
                group.enter()
                s.stop { group.leave() }
            }
            group.notify(queue: .main) { print("Done."); exit(0) }
        }
    }

    // Start mic
    if cfg.mode == .micOnly || cfg.mode == .both {
        let m = MicRecorder(outputURL: URL(fileURLWithPath: cfg.micWavPath))
        micRec = m
        do { try m.start() } catch { fputs("[mic] Error: \(error)\n", stderr) }
    }

    // Start system audio
    if cfg.mode == .sysOnly || cfg.mode == .both {
        let s = SysAudioRecorder(outputURL: URL(fileURLWithPath: cfg.sysWavPath))
        sysRec = s
        Task {
            do {
                try await s.setup()
                try await s.start()
            } catch {
                fputs("[sys] Error: \(error)\n", stderr)
                fputs("[sys] Tip: Grant Screen Recording permission in System Preferences → Privacy & Security\n", stderr)
            }
        }
    }

    RunLoop.main.run()

} else {
    fputs("Error: macOS 12.3+ required.\n", stderr)
    exit(1)
}
