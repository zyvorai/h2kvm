// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev


package domain

// MigrationConfig mirrors the h2kvmctl YAML configuration keys.
// The Go web backend generates this struct, marshals it to YAML,
// and passes it to h2kvmctl --config <file>.
type MigrationConfig struct {
	// Source selection
	Command string `yaml:"command" json:"command"` // local, ova, ovf, vhd, vsphere, azure, fetch-and-fix
	VMDK    string `yaml:"vmdk,omitempty" json:"vmdk,omitempty"`
	OVA     string `yaml:"ova,omitempty" json:"ova,omitempty"`
	OVF     string `yaml:"ovf,omitempty" json:"ovf,omitempty"`
	VHD     string `yaml:"vhd,omitempty" json:"vhd,omitempty"`
	Raw     string `yaml:"raw,omitempty" json:"raw,omitempty"`

	// vSphere
	VSphereHost     string `yaml:"vsphere_host,omitempty" json:"vsphere_host,omitempty"`
	VSphereUsername string `yaml:"vsphere_username,omitempty" json:"vsphere_username,omitempty"`
	VSpherePassword string `yaml:"vsphere_password,omitempty" json:"-"`
	VSphereInsecure bool   `yaml:"vsphere_insecure,omitempty" json:"vsphere_insecure,omitempty"`
	VMPath          string `yaml:"vm_path,omitempty" json:"vm_path,omitempty"`
	Datacenter      string `yaml:"datacenter,omitempty" json:"datacenter,omitempty"`
	VSAction        string `yaml:"vs_action,omitempty" json:"vs_action,omitempty"`

	// Azure
	AzureSubscriptionID string `yaml:"azure_subscription_id,omitempty" json:"azure_subscription_id,omitempty"`
	AzureResourceGroup  string `yaml:"azure_resource_group,omitempty" json:"azure_resource_group,omitempty"`
	AzureVMName         string `yaml:"azure_vm_name,omitempty" json:"azure_vm_name,omitempty"`

	// Output
	OutputDir string `yaml:"output_dir,omitempty" json:"output_dir,omitempty"`
	OutFormat string `yaml:"out_format,omitempty" json:"out_format,omitempty"` // qcow2, raw, vdi
	ToOutput  string `yaml:"to_output,omitempty" json:"to_output,omitempty"`

	// Processing
	Flatten       bool `yaml:"flatten,omitempty" json:"flatten,omitempty"`
	Compress      bool `yaml:"compress,omitempty" json:"compress,omitempty"`
	CompressLevel int  `yaml:"compress_level,omitempty" json:"compress_level,omitempty"`

	// Guest fixes
	FstabMode         string `yaml:"fstab_mode,omitempty" json:"fstab_mode,omitempty"`
	RegenInitramfs    bool   `yaml:"regen_initramfs,omitempty" json:"regen_initramfs,omitempty"`
	UpdateGrub        bool   `yaml:"update_grub,omitempty" json:"update_grub,omitempty"`
	RemoveVMwareTools bool   `yaml:"remove_vmware_tools,omitempty" json:"remove_vmware_tools,omitempty"`
	EnableRDP         bool   `yaml:"enable_rdp,omitempty" json:"enable_rdp,omitempty"`
	GuestOS           string `yaml:"guest_os,omitempty" json:"guest_os,omitempty"`
	SerialConsole     bool   `yaml:"serial_console,omitempty" json:"serial_console,omitempty"`
	UEFI              bool   `yaml:"uefi,omitempty" json:"uefi,omitempty"`

	// Domain / deploy
	EmitDomainXML bool   `yaml:"emit_domain_xml,omitempty" json:"emit_domain_xml,omitempty"`
	VirshDefine   bool   `yaml:"virsh_define,omitempty" json:"virsh_define,omitempty"`
	VMName        string `yaml:"vm_name,omitempty" json:"vm_name,omitempty"`
	Memory        int    `yaml:"memory,omitempty" json:"memory,omitempty"`
	VCPUs         int    `yaml:"vcpus,omitempty" json:"vcpus,omitempty"`
	LibvirtTest   bool   `yaml:"libvirt_test,omitempty" json:"libvirt_test,omitempty"`
	KeepDomain    bool   `yaml:"keep_domain,omitempty" json:"keep_domain,omitempty"`
	QemuTest      bool   `yaml:"qemu_test,omitempty" json:"qemu_test,omitempty"`

	// Kubernetes
	DeployK8s bool   `yaml:"deploy_k8s,omitempty" json:"deploy_k8s,omitempty"`
	Namespace string `yaml:"namespace,omitempty" json:"namespace,omitempty"`

	// OpenStack (Glance upload + optional Nova boot)
	DeployOpenStack           bool   `yaml:"deploy_openstack,omitempty" json:"deploy_openstack,omitempty"`
	GlanceName                string `yaml:"glance_name,omitempty" json:"glance_name,omitempty"`
	OpenStackDescription      string `yaml:"openstack_description,omitempty" json:"openstack_description,omitempty"`
	OpenStackVisibility       string `yaml:"openstack_visibility,omitempty" json:"openstack_visibility,omitempty"`
	OSCloud                   string `yaml:"os_cloud,omitempty" json:"os_cloud,omitempty"`
	OSAuthURL                 string `yaml:"os_auth_url,omitempty" json:"os_auth_url,omitempty"`
	OSUsername                string `yaml:"os_username,omitempty" json:"os_username,omitempty"`
	OSPassword                string `yaml:"os_password,omitempty" json:"-"`
	OSProjectName             string `yaml:"os_project_name,omitempty" json:"os_project_name,omitempty"`
	OpenStackBootInstance     bool   `yaml:"openstack_boot_instance,omitempty" json:"openstack_boot_instance,omitempty"`
	OpenStackServerName       string `yaml:"openstack_server_name,omitempty" json:"openstack_server_name,omitempty"`
	OpenStackFlavor           string `yaml:"openstack_flavor,omitempty" json:"openstack_flavor,omitempty"`
	OpenStackNetwork          string `yaml:"openstack_network,omitempty" json:"openstack_network,omitempty"`
	OpenStackKeyName          string `yaml:"openstack_key_name,omitempty" json:"openstack_key_name,omitempty"`
	OpenStackSecurityGroup    string `yaml:"openstack_security_group,omitempty" json:"openstack_security_group,omitempty"`
	OpenStackAvailabilityZone string `yaml:"openstack_availability_zone,omitempty" json:"openstack_availability_zone,omitempty"`
	OpenStackWait             bool   `yaml:"openstack_wait,omitempty" json:"openstack_wait,omitempty"`

	// Encryption
	LUKSPassphrase string `yaml:"luks_passphrase,omitempty" json:"-"`                      // LUKS disk passphrase
	LUKSKeyfile    string `yaml:"luks_keyfile,omitempty" json:"luks_keyfile,omitempty"`     // Path to LUKS keyfile
	ClevisUnlock   bool   `yaml:"clevis_unlock,omitempty" json:"clevis_unlock,omitempty"`  // Clevis/NBDE auto-unlock
	WinTPM         bool   `yaml:"win_tpm,omitempty" json:"win_tpm,omitempty"`              // Windows TPM 2.0
	WinSecureBoot  *bool  `yaml:"win_secure_boot,omitempty" json:"win_secure_boot,omitempty"` // UEFI Secure Boot (KubeVirt: implies SMM)

	// Security
	AllowedDirs []string `yaml:"allowed_dirs,omitempty" json:"allowed_dirs,omitempty"`

	// Misc
	DryRun  bool   `yaml:"dry_run,omitempty" json:"dry_run,omitempty"`
	Verbose int    `yaml:"verbose,omitempty" json:"verbose,omitempty"`
	Report  string `yaml:"report,omitempty" json:"report,omitempty"`
}
