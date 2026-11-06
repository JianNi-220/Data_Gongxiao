import Foundation
import Vision
import ImageIO

// Usage: ocr manifest.json output_dir [workers]
// Manifest: [{"id":"unique_source_id", "path":"/absolute/image.png"}]
struct Source: Decodable { let id: String; let path: String }
let args = CommandLine.arguments
guard args.count >= 3 else {
    fputs("Usage: ocr manifest.json output_dir [workers]\n", stderr)
    exit(2)
}
let sources = try JSONDecoder().decode([Source].self, from: Data(contentsOf: URL(fileURLWithPath: args[1])))
let output = URL(fileURLWithPath: args[2], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let workers = max(1, Int(args.count > 3 ? args[3] : "2") ?? 2)
let queue = OperationQueue()
queue.maxConcurrentOperationCount = workers
let lock = NSLock()
var finished = 0
var failed = 0
let started = Date()
for source in sources {
    guard !source.id.isEmpty, source.id.range(of: "^[A-Za-z0-9_-]+$", options: .regularExpression) != nil else {
        fatalError("Source id must contain only letters, digits, _ or -")
    }
    queue.addOperation {
        autoreleasepool {
            let destination = output.appendingPathComponent(source.id + ".json")
            if let data = try? Data(contentsOf: destination),
               let existing = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               existing["status"] as? String == "ok" {
                lock.lock(); finished += 1; lock.unlock()
                return
            }
            var record: [String: Any] = ["id": source.id, "source_path": source.path,
                "engine": "Apple Vision VNRecognizeTextRequest", "recognition_level": "accurate",
                "recognition_languages": ["zh-Hans", "en-US"], "uses_language_correction": false,
                "bbox_origin": "bottom_left", "bbox_units": "normalized"]
            do {
                let imageURL = URL(fileURLWithPath: source.path)
                if let image = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
                   let properties = CGImageSourceCopyPropertiesAtIndex(image, 0, nil) as? [CFString: Any] {
                    record["image_width"] = properties[kCGImagePropertyPixelWidth]
                    record["image_height"] = properties[kCGImagePropertyPixelHeight]
                }
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .accurate
                request.recognitionLanguages = ["zh-Hans", "en-US"]
                request.usesLanguageCorrection = false
                try VNImageRequestHandler(url: imageURL, options: [:]).perform([request])
                record["revision"] = request.revision
                record["observations"] = (request.results ?? []).compactMap { observation -> [String: Any]? in
                    guard let candidate = observation.topCandidates(1).first else { return nil }
                    let box = observation.boundingBox
                    var line: [String: Any] = ["text": candidate.string, "confidence": candidate.confidence,
                        "bbox": ["x": box.minX, "y": box.minY, "width": box.width, "height": box.height]]
                    if candidate.string.count <= 30 {
                        line["characters"] = candidate.string.indices.compactMap { index -> [String: Any]? in
                            let next = candidate.string.index(after: index)
                            guard let characterBox = try? candidate.boundingBox(for: index..<next) else { return nil }
                            let b = characterBox.boundingBox
                            return ["text": String(candidate.string[index..<next]),
                                "bbox": ["x": b.minX, "y": b.minY, "width": b.width, "height": b.height]]
                        }
                    }
                    return line
                }
                record["status"] = "ok"
            } catch {
                record["status"] = "error"
                record["error"] = String(describing: error)
            }
            do {
                let data = try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
                try data.write(to: destination, options: .atomic)
            } catch {
                fputs("Unable to save \(source.id): \(error)\n", stderr)
            }
            lock.lock()
            finished += 1
            if record["status"] as? String != "ok" { failed += 1 }
            if finished % 20 == 0 || finished == sources.count {
                fputs("OCR \(finished)/\(sources.count), errors \(failed), elapsed \(Int(Date().timeIntervalSince(started)))s\n", stderr)
            }
            lock.unlock()
        }
    }
}
queue.waitUntilAllOperationsAreFinished()
fputs("Done \(finished) images, errors \(failed), elapsed \(String(format: "%.2f", Date().timeIntervalSince(started)))s\n", stderr)
exit(failed == 0 ? 0 : 1)
