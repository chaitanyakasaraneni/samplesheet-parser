process SAMPLESHEETPARSER_DIFF {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/samplesheet-parser:1.2.0--pyhdfd78af_0' :
        'biocontainers/samplesheet-parser:1.2.0--pyhdfd78af_0' }"

    input:
    tuple val(meta), path(old_sheet), path(new_sheet)

    output:
    tuple val(meta), path("*.diff.json"), emit: json
    path "versions.yml",                  emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args   = task.ext.args   ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    samplesheet diff \\
        --format json \\
        ${args} \\
        ${old_sheet} ${new_sheet} > ${prefix}.diff.json || true

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        samplesheet-parser: \$(samplesheet --version | sed 's/samplesheet-parser //')
    END_VERSIONS
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    echo '{"has_changes": false, "header_changes": [], "samples_added": [], "samples_removed": [], "sample_changes": []}' > ${prefix}.diff.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        samplesheet-parser: \$(samplesheet --version | sed 's/samplesheet-parser //')
    END_VERSIONS
    """
}
