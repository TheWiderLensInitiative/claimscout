package info.thewiderlens.claimscout.ui

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import info.thewiderlens.claimscout.BuildConfig
import info.thewiderlens.claimscout.ClaimScoutApp
import info.thewiderlens.claimscout.data.Api
import info.thewiderlens.claimscout.data.ApiException
import info.thewiderlens.claimscout.data.Claim
import info.thewiderlens.claimscout.data.Detail
import info.thewiderlens.claimscout.data.MailAccount
import info.thewiderlens.claimscout.data.Pairing
import info.thewiderlens.claimscout.data.Profile
import info.thewiderlens.claimscout.data.Row
import info.thewiderlens.claimscout.data.Status
import info.thewiderlens.claimscout.data.parsePairLink
import info.thewiderlens.claimscout.mail.Gmail
import info.thewiderlens.claimscout.mail.MailSearch
import info.thewiderlens.claimscout.mail.Outlook
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

enum class Tab(val label: String, val view: String) { Matches("For you", "matches"), Browse("Browse", "all"), Claims("My claims", "claimed"), Settings("Settings", "") }

class Vm(app: Application) : AndroidViewModel(app) {
    val store = (app as ClaimScoutApp).store
    val pairing = store.pairingFlow.stateIn(viewModelScope, SharingStarted.Eagerly, null)
    val accounts = store.accountsFlow.stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())
    var loaded by mutableStateOf(false)

    var tab by mutableStateOf(Tab.Matches)
    var rows by mutableStateOf<List<Row>>(emptyList())
    var status by mutableStateOf<Status?>(null)
    var query by mutableStateOf("")
    var noProofOnly by mutableStateOf(false)
    var detail by mutableStateOf<Detail?>(null)
    var openId by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var proofNote by mutableStateOf<String?>(null)
    var findingProof by mutableStateOf(false)
    var profile by mutableStateOf<Profile?>(null)

    // Outlook sign-in in progress
    var outlookCode by mutableStateOf<Outlook.DeviceCode?>(null)
    var msClientId by mutableStateOf(BuildConfig.MS_CLIENT_ID)

    init {
        viewModelScope.launch {
            if (msClientId.isEmpty()) msClientId = store.msClientId()
            loaded = true
            if (store.pairing() != null) reload()
        }
    }

    private suspend fun api(): Api {
        val p = store.pairing() ?: throw ApiException("Not paired")
        return Api(p) { good -> store.setPairing(p.copy(lastGood = good)) }
    }

    private fun launch(block: suspend () -> Unit): Job = viewModelScope.launch {
        busy = true; error = null
        try { block() } catch (e: Exception) {
            error = e.message ?: e.toString()
            if (e is ApiException && e.code == 401) store.setPairing(null)
        } finally { busy = false }
    }

    fun pair(link: String): Boolean {
        val p: Pairing = parsePairLink(link) ?: run { error = "That isn't a ClaimScout pairing link."; return false }
        launch {
            Api(p).status()   // proves the token and certificate before saving
            store.setPairing(p)
            reload()
        }
        return true
    }

    fun unpair() = launch { store.setPairing(null); rows = emptyList(); status = null }

    fun reload() = launch {
        val a = api()
        status = a.status()
        rows = when (tab) {
            Tab.Settings -> rows
            Tab.Browse -> a.settlements(if (noProofOnly) "noproof" else "all", query)
            else -> a.settlements(tab.view)
        }
    }

    fun select(t: Tab) {
        tab = t
        if (t == Tab.Settings) loadProfile() else reload()
    }

    fun open(id: String?) {
        openId = id; detail = null; proofNote = null
        if (id != null) launch { detail = api().detail(id) }
    }

    fun refreshDetail() = openId?.let { id -> launch { detail = api().detail(id) } }

    fun dismiss(id: String) = launch { api().dismiss(id); open(null); reload() }
    fun recheck(id: String) = launch { api().rematch(id); detail = api().detail(id) }

    fun saveClaim(id: String, c: Claim?) = launch {
        if (c == null) api().deleteClaim(id) else api().saveClaim(id, c)
        detail = api().detail(id)
    }

    fun deleteProof(pid: Long) = launch { api().deleteProof(pid); refreshDetail() }

    /** Search this phone's connected inboxes with the settlement's plan; the PC keeps what proves something. */
    fun findProof() {
        val d = detail ?: return
        val plan = d.proof_plan
        if (accounts.value.isEmpty()) { proofNote = "Connect Gmail or Outlook in Settings first."; return }
        if (plan == null || (plan.senders.isEmpty() && plan.keywords.isEmpty())) {
            proofNote = "There's nothing to search email for on this one."; return
        }
        findingProof = true
        launch {
            try {
                val r = MailSearch(store).run(plan)
                val result = if (r.messages.isEmpty()) "No matching emails in ${r.searched.joinToString()}." else {
                    val kept = api().addProof(d.id, r.messages)
                    "Checked ${r.messages.size} email(s); ${kept.size} look like proof."
                }
                proofNote = (listOf(result) + r.errors).joinToString("\n")
                detail = api().detail(d.id)
            } finally { findingProof = false }
        }
    }

    fun loadProfile() = launch { profile = api().profile() }
    fun saveProfile(p: Profile) = launch { api().saveProfile(p); profile = p; status = api().status() }
    fun checkNow() = launch { api().refresh() }

    fun addGmail(address: String, appPassword: String, done: () -> Unit) = launch {
        Gmail.verify(address.trim(), appPassword)
        store.saveAccount(MailAccount("gmail", address.trim(), appPassword.replace(" ", "")))
        done()
    }

    fun startOutlook() = launch {
        if (msClientId.isBlank()) throw IllegalStateException("Paste your Microsoft app's client ID first (see the help link).")
        store.setMsClientId(msClientId)
        val dc = Outlook.start(msClientId.trim())
        outlookCode = dc
        try {
            store.saveAccount(Outlook.finish(msClientId.trim(), dc))
        } finally { outlookCode = null }
    }

    fun removeAccount(a: MailAccount) = launch { store.removeAccount(a) }
}
