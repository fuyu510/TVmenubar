import Foundation

enum AppResources {
    static let bundle: Bundle = {
        // Packaged apps use Contents/Resources; SwiftPM runs use its module bundle.
        if let resources = Bundle.main.resourceURL,
           let packaged = Bundle(url: resources.appendingPathComponent("LGwebOSMenubar_LGwebOSMenubar.bundle")) {
            return packaged
        }
        return Bundle.module
    }()
}
