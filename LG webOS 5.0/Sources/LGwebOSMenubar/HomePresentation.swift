import Foundation

/// SSAP reports the underlying app while webOS 5's Home overlay is visible.
/// This tracks a successful Home command, not independently confirmed visibility.
struct HomePresentation {
    private(set) var requested = false
    private var underlyingID = ""
    mutating func didSendHome(underlyingID: String) {
        requested = true
        self.underlyingID = underlyingID
    }
    mutating func observe(appID: String) {
        if requested && appID != underlyingID { dismiss() }
    }
    mutating func dismiss() { requested = false; underlyingID = "" }
}
