// On-device text recognition (Apple Vision). swift vision.swift img.png [digits]
import Foundation
import Vision
import AppKit
let args = CommandLine.arguments
let url = URL(fileURLWithPath: args[1])
guard let ns = NSImage(contentsOf: url), let cg = ns.cgImage(forProposedRect: nil, context: nil, hints: nil) else { exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
req.recognitionLanguages = ["sv-SE", "en-US"]
if #available(macOS 13.0, *) { req.revision = VNRecognizeTextRequestRevision3 }
try VNImageRequestHandler(cgImage: cg).perform([req])
for o in req.results ?? [] {
  let cands = o.topCandidates(3).map { "\($0.string)|\(String(format: "%.2f", $0.confidence))" }
  let b = o.boundingBox
  print(String(format: "%.3f %.3f %.3f %.3f\t", b.minX, 1 - b.maxY, b.width, b.height) + cands.joined(separator: "  "))
}
